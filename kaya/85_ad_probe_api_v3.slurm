#!/bin/bash --login
#SBATCH --job-name=t2c_ad_probe_api_v3
#SBATCH --partition=work
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 8.3 — Gate G3 (API): v3 ambiguity-detector stratified probe with the `kind: api` model as
# BOTH the SchemaLinker (per the 8.2 ad_probe_v3.py generalisation) and the AD/Dis backend — the
# API-AD leg 7.5 explicitly deferred. The GPU-free sibling of kaya/80_ad_probe_v3.slurm: with the
# SL resolved from the registry as an API model (temperature sampling, instruct prompt), NO GPU is
# needed, so `--partition=work`, no `--gres`. A live v3 Neo4j IS still required (Entity Lookup), so
# the v3 graph runs in the BACKGROUND in this same job (SEPARATE $MYGROUP/neo4j_data_v3 volume).
# Reuses the existing v3 volume; pass RELOAD=1 to wipe+reload the current v3 cypher first.
# Submit from repo root (export the key FIRST):
#   ANTHROPIC_API_KEY=... sbatch kaya/85_ad_probe_api_v3.slurm

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

if [[ "${RELOAD:-0}" -eq 1 || ! -d "$DATA/data/databases" ]]; then
    echo "Wiping v3 volume $DATA and reloading $CYPHER."
    rm -rf "$DATA"; FRESH=1
else
    echo "Reusing existing v3 volume at $DATA."; FRESH=0
fi
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"

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

# ── AD probe: API SL + API AD/Dis (no GPU) ───────────────────────────────────────
MODEL_KEY="${MODEL_KEY:-claude-sonnet}"
python kaya/ad_probe_v3.py --model_key "$MODEL_KEY" \
    --ad_backend api --ad_model "${AD_MODEL:-$MODEL_KEY}"
echo "Finished at $(date)"
