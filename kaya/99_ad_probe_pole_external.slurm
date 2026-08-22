#!/bin/bash --login
#SBATCH --job-name=t2c_ad_probe_pole_external
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
# Step 10.4 — Gate G3: external-POLE ambiguity-detector stratified probe. Needs BOTH a GPU
# (SchemaLinker sl_adapter_pole_external + base Mistral as the AD LLM) AND a live external-POLE
# Neo4j (Entity Lookup) — so the external graph runs in the BACKGROUND inside this same GPU job,
# pointed at the SEPARATE $MYGROUP/neo4j_data_pole_external dir (10.1; NOT the v2/v3 volumes).
# Reuses the existing external volume by default (loaded by 10.1's 90_neo4j_pole_external.slurm);
# pass RELOAD=1 to wipe + reload from $MYGROUP/dumps/pole-external/neo4j.dump first.
#
# Base-model AD (default):   sbatch kaya/99_ad_probe_pole_external.slurm
# API AD (needs API key):    AD_BACKEND=api AD_MODEL=claude-sonnet sbatch kaya/99_ad_probe_pole_external.slurm
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

# ── AD probe ─────────────────────────────────────────────────────────────────────
AD_ARGS="--ad_backend ${AD_BACKEND:-base}"
if [[ "${AD_BACKEND:-base}" == "api" ]]; then
    AD_ARGS="$AD_ARGS --ad_model ${AD_MODEL:?set AD_MODEL for api backend}"
fi
python kaya/ad_probe_pole_external.py --model_key mistral7b $AD_ARGS
echo "Finished at $(date)"
