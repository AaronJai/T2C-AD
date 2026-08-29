#!/bin/bash --login
#SBATCH --job-name=t2c_ad_probe_pole_external_qwen
#SBATCH --partition=rrifcs
#SBATCH --time=03:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100:1
#SBATCH --mem=96G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.7 — Gate G3: external-POLE ambiguity-detector stratified probe for QWEN2.5-32B. Same
# harness as 10.4's kaya/99_ad_probe_pole_external.slurm (kaya/ad_probe_pole_external.py already
# takes --model_key); differs only in the model key, the H100 partition, and the Neo4j isolation.
#
# Needs BOTH a GPU (SchemaLinker sl_adapter_pole_external + base Qwen as the AD LLM — two 4-bit
# 32B loads, ~40 GiB, hence an H100 NVL rather than a 16 GB V100) AND a live external-POLE Neo4j
# (Entity Lookup) — so the 10.1 external graph runs in the BACKGROUND inside this same GPU job.
#
# NEO4J ISOLATION: its OWN data dir ($MYGROUP/neo4j_data_pole_external_qwen_ad), loaded from the
# staged dump, rather than the shared neo4j_data_pole_external — so a co-located job can never be
# writing the same store (kaya/91, 2026-07-17). It CANNOT get its own Bolt port: the harness
# hardcodes bolt://localhost:7687. **Do not co-schedule with kaya/107 or any other :7687 binder
# on the same node** — run them one after the other; a second binder makes the readiness loop
# below abort the job loudly after 180 s rather than corrupting anything.
#
# Counts are RECORDED, not a numeric gate (10.4 precedent: base Mistral scored 6/10 here, its
# 4 TPs all firing via the entity_entropy fallback).
#
# Base-model AD (default):  sbatch kaya/108_ad_probe_pole_external_qwen.slurm
# API AD (needs API key):   AD_BACKEND=api AD_MODEL=claude-sonnet sbatch kaya/108_ad_probe_pole_external_qwen.slurm
# Submit from repo root.

set -euo pipefail

MODEL_KEY="${MODEL_KEY:-qwen2.5-32b}"

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

# ── external-POLE Neo4j in the background, own data dir, fixed Bolt :7687 (see header) ────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_pole_external${NEO4J_DATA_SUFFIX:-_qwen_ad}"
DUMP_DIR="$GROUP/dumps/pole-external"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"
NEO4J_URI="bolt://localhost:7687"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi
if [[ ! -f "$DUMP_DIR/neo4j.dump" ]]; then
    echo "Missing $DUMP_DIR/neo4j.dump — stage the upstream pole-50.dump (see kaya/90 header)." >&2
    exit 1
fi

# Reuse this runner's own volume if it already holds the loaded store; RELOAD=1 forces a reload.
if [[ "${RELOAD:-0}" -eq 1 || ! -d "$DATA/data/databases" ]]; then
    echo "Wiping $DATA and loading from $DUMP_DIR/neo4j.dump."
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

cshell() { apptainer exec --no-mount /opt "$SIF" cypher-shell -a "$NEO4J_URI" "$@"; }

NEO4J_READY=0
for i in $(seq 1 90); do
    if cshell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        echo "Neo4j ready after ${i} checks on ${NEO4J_URI}."; NEO4J_READY=1; break
    fi
    sleep 2
done
if [[ "$NEO4J_READY" -ne 1 ]]; then
    echo "Neo4j never became ready on ${NEO4J_URI} after 180s — aborting." >&2
    exit 1
fi

echo "── Graph spot-check (expect nodes 61521) ──"
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n) AS nodes;" || true

# ── AD probe ─────────────────────────────────────────────────────────────────────
AD_ARGS="--ad_backend ${AD_BACKEND:-base}"
if [[ "${AD_BACKEND:-base}" == "api" ]]; then
    AD_ARGS="$AD_ARGS --ad_model ${AD_MODEL:?set AD_MODEL for api backend}"
fi
python kaya/ad_probe_pole_external.py --model_key "$MODEL_KEY" $AD_ARGS
echo "Finished at $(date)"
