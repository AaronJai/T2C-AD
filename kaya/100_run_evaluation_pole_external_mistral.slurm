#!/bin/bash --login
#SBATCH --job-name=t2c_run_eval_pole_external_mistral
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
# Step 10.4 — Gate G4: the full end-to-end evaluation of the FINE-TUNED 7B Mistral against the
# external POLE benchmark. run_evaluation reads config/pipeline_pole_external_mistral.yaml
# (dataset_version: pole_external → external schema/registry/prompts + `_pole_external` adapters
# via adapter_suffix_for_version; results_tag: pole_external_mistral → results/
# tables_mistral7b_pole_external_mistral.md + metrics_mistral7b_pole_external_mistral.json +
# qual_records_mistral7b_pole_external_mistral.json), over all 100 external-POLE questions × 3
# conditions. Then analyze_qualitative.py builds the qualitative report from the qual records.
#
# NOTE (spec name): the 10.4 spec named this runner kaya/96_run_evaluation_pole_external_mistral
# .slurm; 96_/97_ were subsequently claimed by 10.3 (sl cov check / qwen fit test), so this is
# renumbered to 100_ (decisions-log 2026-08-22). Same contents the spec describes.
#
# Needs BOTH a GPU and a live external-POLE Neo4j — so the external graph (10.1) runs in the
# BACKGROUND inside this same GPU job, pointed at the SEPARATE $MYGROUP/neo4j_data_pole_external
# dir (NOT the v2/v3 volumes). Reuses the existing external volume by default (loaded by 10.1's
# 90 runner); RELOAD=1 wipes + reloads from $MYGROUP/dumps/pole-external/neo4j.dump first.
# Submit from repo root:  sbatch kaya/100_run_evaluation_pole_external_mistral.slurm
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

# ── external-POLE Neo4j in the background (same node → bolt://localhost:7687) ──────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_pole_external"
DUMP_DIR="$GROUP/dumps/pole-external"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi

# Reuse the existing external volume by default (loaded by 10.1); RELOAD=1 wipes + reloads the dump.
if [[ "${RELOAD:-0}" -eq 1 || ! -d "$DATA/data/databases" ]]; then
    if [[ ! -f "$DUMP_DIR/neo4j.dump" ]]; then
        echo "Missing $DUMP_DIR/neo4j.dump — stage the upstream pole-50.dump (see 90 header)." >&2
        exit 1
    fi
    echo "Wiping external volume $DATA and loading from $DUMP_DIR/neo4j.dump."
    rm -rf "$DATA"; FRESH=1
else
    echo "Reusing existing external-POLE volume at $DATA."; FRESH=0
fi
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"

APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins"
    --bind "$DUMP_DIR:/dumps")

if [[ "$FRESH" -eq 1 ]]; then
    echo "Fresh volume — setting initial password + loading the dump (offline store) BEFORE console"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" \
        neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination
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

echo "── Graph spot-check (expect nodes 61521, relationships ~105840) ──"
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n) AS nodes;" || true

# ── Full external-POLE evaluation with the fine-tuned Mistral (C1 → C2 → C3 over 100 Qs) ──
python -m experiments.run_evaluation config/pipeline_pole_external_mistral.yaml

echo "Wrote results/tables_mistral7b_pole_external_mistral.md + metrics_/qual_records_ ..."

# ── Qualitative analysis on the qual records (per-type buckets) ────────────────────
python -m experiments.analyze_qualitative \
    results/qual_records_mistral7b_pole_external_mistral.json

echo "Wrote results/qualitative_analysis_mistral7b_pole_external_mistral.md"
echo "Finished at $(date)"
