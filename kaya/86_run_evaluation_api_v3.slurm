#!/bin/bash --login
#SBATCH --job-name=t2c_run_eval_api_v3
#SBATCH --partition=work
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 8.3 — Gate G4 (API): the full end-to-end evaluation on the `kind: api` model over the v3
# substrate. Combines kaya/81_run_evaluation_v3.slurm's v3 Neo4j block (the SEPARATE
# $MYGROUP/neo4j_data_v3 volume) with kaya/67's GPU-free `--partition=work` + API-key guard.
# One model runs every stage; the SL gets its candidate distribution by TEMPERATURE SAMPLING, so
# NO GPU is needed. A live v3 Neo4j IS required (Entity Lookup, CyVer schema/props, DB executor,
# ground-truth execution), so the v3 graph runs in the BACKGROUND in this same job.
#
# run_evaluation reads config/pipeline.yaml (dataset_version: v3 → v3 schema/registry/prompts;
# results_tag: v3 → results/tables_claude-sonnet_v3.md + metrics_claude-sonnet_v3.json). 8.3 flips
# config/pipeline.yaml `active_model: claude-sonnet` (config-only) before submitting.
# Reloads the current data/SyntheticPoliceKG-v3.cypher by default; KEEP=1 reuses the volume.
# Submit from repo root (export the key FIRST):
#   ANTHROPIC_API_KEY=... sbatch kaya/86_run_evaluation_api_v3.slurm

set -euo pipefail

module load Anaconda3/2024.06
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
unset LD_PRELOAD

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

if [[ -z "${ANTHROPIC_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
    echo "No ANTHROPIC_API_KEY or OPENAI_API_KEY in the environment — export one before sbatch." >&2
    exit 1
fi

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

# ── Run the full v3 evaluation via the API model (C1 → C2 → C3 over all 120 questions) ──
python -m experiments.run_evaluation config/pipeline.yaml

echo "Wrote results/tables_<active_model>_v3.md + results/metrics_<active_model>_v3.json"
echo "Finished at $(date)"
