#!/bin/bash --login
#SBATCH --job-name=t2c_run_evaluation_v3
#SBATCH --partition=gpu
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:2
#SBATCH --mem=96G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.5 — Gate G4: the full end-to-end evaluation on the v3 substrate. run_evaluation reads
# config/pipeline.yaml (dataset_version: v3 → v3 schema/registry/prompts + `_v3` adapters via
# adapter_suffix_for_version; results_tag: v3 → results/tables_mistral7b_v3.md +
# metrics_mistral7b_v3.json), over all 120 v3 questions × 3 conditions. Needs BOTH a GPU and a
# live v3 Neo4j — so the v3 graph runs in the BACKGROUND inside this same GPU job, pointed at
# the SEPARATE $MYGROUP/neo4j_data_v3 dir (NOT the v2 neo4j_data used by 65). Reloads the current
# data/SyntheticPoliceKG-v3.cypher by default so the run always serves the current v3 seed data;
# KEEP=1 reuses the existing v3 volume.
# Submit from repo root:  sbatch kaya/81_run_evaluation_v3.slurm
#
# 4-bit/fp16 loads (registry) → C2 ≈ 9 GB, C3 ≈ 14 GB; gpu:2 lets build_condition3 pin
# SL→cuda:0, QG+AD→cuda:1 for C3's beam_k=5 KV spikes (decisions-log 2026-06-26).

set -euo pipefail

module load Anaconda3/2024.06
module load cuda/12.6.3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset LD_PRELOAD

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"
nvidia-smi

# ── v3 Neo4j in the background (same node → bolt://localhost:7687) ────────────────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_v3"
CYPHER="data/SyntheticPoliceKG-v3.cypher"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi

# Wipe+reload by default (serve current v3 seed data); KEEP=1 reuses the existing volume.
if [[ "${KEEP:-0}" -eq 1 && -d "$DATA/data/databases" ]]; then
    FRESH=0
    echo "KEEP=1 — reusing existing v3 volume at $DATA (no reload)."
else
    echo "Wiping v3 volume $DATA and reloading $CYPHER."
    rm -rf "$DATA"; FRESH=1
fi
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"

APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins")

if [[ "$FRESH" -eq 1 ]]; then
    echo "Fresh volume — setting initial password via neo4j-admin"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"
fi

apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j console &
NEO4J_PID=$!
cleanup() {
    echo "Stopping neo4j (pid $NEO4J_PID) at $(date)"
    kill "$NEO4J_PID" 2>/dev/null || true
    wait "$NEO4J_PID" 2>/dev/null || true
}
trap cleanup EXIT

cshell() { apptainer exec --no-mount /opt "$SIF" cypher-shell -a bolt://localhost:7687 "$@"; }

for i in $(seq 1 90); do
    if cshell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        echo "Neo4j ready after ${i} checks."; break
    fi
    sleep 2
done

if [[ "$FRESH" -eq 1 ]]; then
    echo "Loading $CYPHER"
    cshell -u neo4j -p "$NEO4J_PASSWORD" --file "$CYPHER"
    echo "v3 graph loaded."
else
    echo "Reusing existing v3 DB volume — skipping load."
fi

# ── Run the full v3 evaluation (C1 → C2 → C3 over all 120 questions) ─────────────
python -m experiments.run_evaluation config/pipeline.yaml

echo "Wrote results/tables_mistral7b_v3.md + results/metrics_mistral7b_v3.json"
echo "Finished at $(date)"
