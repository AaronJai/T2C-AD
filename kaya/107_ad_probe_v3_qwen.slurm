#!/bin/bash --login
#SBATCH --job-name=t2c_ad_probe_v3_qwen
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
# Step 10.7 — Gate G3: v3 ambiguity-detector stratified probe for QWEN2.5-32B. Same harness as
# 7.5's kaya/80_ad_probe_v3.slurm (kaya/ad_probe_v3.py already takes --model_key, so nothing
# Qwen-specific is added); differs only in the model key, the H100 partition, and the Neo4j
# isolation below.
#
# Needs BOTH a GPU (SchemaLinker sl_adapter_v3 + base Qwen as the AD LLM — two 4-bit 32B loads,
# ~40 GiB, which is why this asks for an H100 NVL, not a 16 GB V100) AND a live v3 Neo4j (Entity
# Lookup) — so the v3 graph runs in the BACKGROUND inside this same GPU job.
#
# NEO4J ISOLATION: this job gets its OWN data dir ($MYGROUP/neo4j_data_v3_qwen_ad) rather than
# the shared neo4j_data_v3, so a co-located job can never be writing the same store — kaya/91's
# 2026-07-17 finding. It CANNOT get its own Bolt port: kaya/ad_probe_v3.py (7.5) hardcodes
# bolt://localhost:7687 and adding a --neo4j_uri flag would mean editing a harness outside this
# step's scope. **Do not co-schedule this with kaya/108 (the external AD probe) or any other
# :7687 binder on the same node** — run them one after the other. If you do, the second server
# fails to bind and the readiness loop below aborts the job loudly after 180 s; separate data
# dirs mean it can never silently write into the other job's database.
#
# Counts are RECORDED, not a numeric gate (7.5/10.4 precedent — the base 7B under-detects and
# falls back to entropy; the open question here is whether a 32B base parses the AD JSON at all).
#
# Base-model AD (default):  sbatch kaya/107_ad_probe_v3_qwen.slurm
# API AD (needs API key):   AD_BACKEND=api AD_MODEL=claude-sonnet sbatch kaya/107_ad_probe_v3_qwen.slurm
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

# ── v3 Neo4j in the background, isolated data dir, fixed Bolt :7687 (see header) ──────────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_v3${NEO4J_DATA_SUFFIX:-_qwen_ad}"
CYPHER="data/SyntheticPoliceKG-v3.cypher"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

NEO4J_URI="bolt://localhost:7687"      # fixed: the AD-probe harness hardcodes this (see header)

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi

echo "Wiping v3 volume $DATA and reloading $CYPHER (Bolt ${NEO4J_URI})."
rm -rf "$DATA"
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"

APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins")

apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"

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

echo "Loading $CYPHER"
cshell -u neo4j -p "$NEO4J_PASSWORD" --file "$CYPHER"
echo "v3 graph loaded."

# ── AD probe ─────────────────────────────────────────────────────────────────────
AD_ARGS="--ad_backend ${AD_BACKEND:-base}"
if [[ "${AD_BACKEND:-base}" == "api" ]]; then
    AD_ARGS="$AD_ARGS --ad_model ${AD_MODEL:?set AD_MODEL for api backend}"
fi
python kaya/ad_probe_v3.py --model_key "$MODEL_KEY" $AD_ARGS
echo "Finished at $(date)"
