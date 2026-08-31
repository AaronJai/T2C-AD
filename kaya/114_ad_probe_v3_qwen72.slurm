#!/bin/bash --login
#SBATCH --job-name=t2c_ad_probe_v3_qwen72
#SBATCH --partition=rrifcs
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100:1
#SBATCH --mem=200G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 11.4 — Gate G3: v3 ambiguity-detector stratified probe for QWEN2.5-72B. Same harness as
# 7.5's kaya/80_ad_probe_v3.slurm and 10.7's kaya/107 (kaya/ad_probe_v3.py already takes
# --model_key, so nothing 72B-specific is added); differs only in the model key, the walltime and
# memory, and its own Neo4j volume.
#
# Needs BOTH a GPU (SchemaLinker sl_adapter_v3 + base Qwen-72B as the AD LLM) AND a live v3 Neo4j
# (Entity Lookup) — so the v3 graph runs in the BACKGROUND inside this same GPU job.
#
# ONE CARD IS ENOUGH, and that is a property of the harness, not an assumption: ad_probe_v3.py
# runs the SL leg to completion, then `del sl_llm, linker` + `torch.cuda.empty_cache()` BEFORE
# building the AD LLM — so only ONE 11.2-measured 42.5 GiB 4-bit load is resident at a time on a
# 93.1 GiB H100 NVL. (Two co-resident 72B loads would be ~85 GiB before any KV cache; that is the
# arrangement 11.4 gives a third card to in build_condition3._device_maps(), and it does not
# arise here.) Host RAM is raised to 200G to match 11.3's per-job request for a 37-shard load.
#
# NEO4J ISOLATION: this job gets its OWN data dir ($MYGROUP/neo4j_data_v3_qwen72_ad) rather than
# the shared neo4j_data_v3 or 10.7's _qwen_ad volume, so a co-located job can never be writing the
# same store — kaya/91's 2026-07-17 finding. It CANNOT get its own Bolt port: kaya/ad_probe_v3.py
# (7.5) hardcodes bolt://localhost:7687 and adding a --neo4j_uri flag would mean editing a harness
# outside this step's scope. **Do not co-schedule this with kaya/115 (the external AD probe) or
# any other :7687 binder on the same node** — run them one after the other. If you do, the second
# server fails to bind and the readiness loop below aborts the job loudly after 180 s; separate
# data dirs mean it can never silently write into the other job's database.
#
# WALLTIME: 10 stratified items x 11.2's measured 29.6 s per k=5 SL decode, plus the AD's own
# generation and TWO sequential 4-bit loads of a 37-shard model. 10.7's 32B run took 5m05s; 6 h is
# deliberate slack, not an estimate.
#
# Counts are RECORDED, not a numeric gate (7.5/10.4/10.7 precedent). The open question the 32B
# raised: it was the first LOCAL model to emit well-formed AD JSON with substantive rationales
# (8/10 on v3) where every base-7B run fell back to `entity_entropy` — does 2.2x more scale hold
# or improve that?
#
# Base-model AD (default):  sbatch kaya/114_ad_probe_v3_qwen72.slurm
# API AD (needs API key):   AD_BACKEND=api AD_MODEL=claude-sonnet sbatch kaya/114_ad_probe_v3_qwen72.slurm
# Submit from repo root.

set -euo pipefail

MODEL_KEY="${MODEL_KEY:-qwen2.5-72b}"

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
DATA="$GROUP/neo4j_data_v3${NEO4J_DATA_SUFFIX:-_qwen72_ad}"
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
