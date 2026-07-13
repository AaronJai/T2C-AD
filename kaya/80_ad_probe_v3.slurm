#!/bin/bash --login
#SBATCH --job-name=t2c_ad_probe_v3
#SBATCH --partition=gpu
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.5 — Gate G3: v3 ambiguity-detector stratified probe. Needs BOTH a GPU (SchemaLinker
# sl_adapter_v3 + base as the AD LLM) AND a live v3 Neo4j (Entity Lookup) — so the v3 graph runs
# in the BACKGROUND inside this same GPU job, pointed at the SEPARATE $MYGROUP/neo4j_data_v3 dir
# (NOT the v2 neo4j_data). Reuses the existing v3 volume (loaded by 72/70); pass RELOAD=1 to
# wipe+reload the current data/SyntheticPoliceKG-v3.cypher first.
#
# Base-model AD (default):   sbatch kaya/80_ad_probe_v3.slurm
# API AD (needs API key):    AD_BACKEND=api AD_MODEL=claude-sonnet sbatch kaya/80_ad_probe_v3.slurm
# Submit from repo root.

set -euo pipefail

module load Anaconda3/2024.06
module load cuda/12.6.3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
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

if [[ "${RELOAD:-0}" -eq 1 || ! -d "$DATA/data/databases" ]]; then
    echo "Wiping v3 volume $DATA and reloading $CYPHER."
    rm -rf "$DATA"; FRESH=1
    mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"
else
    echo "Reusing existing v3 volume at $DATA."; FRESH=0
    mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"
fi

APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins")

if [[ "$FRESH" -eq 1 ]]; then
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
fi

# ── AD probe ─────────────────────────────────────────────────────────────────────
AD_ARGS="--ad_backend ${AD_BACKEND:-base}"
if [[ "${AD_BACKEND:-base}" == "api" ]]; then
    AD_ARGS="$AD_ARGS --ad_model ${AD_MODEL:?set AD_MODEL for api backend}"
fi
python kaya/ad_probe_v3.py --model_key mistral7b $AD_ARGS
echo "Finished at $(date)"
