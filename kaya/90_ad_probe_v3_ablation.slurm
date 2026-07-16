#!/bin/bash --login
#SBATCH --job-name=t2c_ad_probe_v3_ablation
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
# Ablation (decisions-log only, no new phase spec) — the detection-side counterpart to
# 87/88_g1_coverage_v3_*.slurm. Runs the SAME 10-question stratified AD probe as 7.5 G3
# (kaya/ad_probe_v3.py, base-model AD, live v3 Neo4j) but with the SL pointed at a WEAKER
# adapter, holding the base (non-instruct) AD fixed. Tests directly whether detection
# specifically survives degraded SL quality, rather than inferring it from Cov@5 alone —
# because v3-mistral (Cov@5 0.725, base AD, recall 19.2%) vs v3-claude-sonnet (similar/lower
# Cov@5, instruct AD, recall 66.2%) leaves it ambiguous whether SL quality or AD-model
# reasoning capability is the dominant lever for detection.
#
# Generic-Ozsoy-only SL (Cov@5 0.483 on v3):  SL_ADAPTER_SUFFIX="" sbatch kaya/90_ad_probe_v3_ablation.slurm
# No SL adapter at all (Cov@5 0.000 on v3):   NO_SL_ADAPTER=1 sbatch kaya/90_ad_probe_v3_ablation.slurm
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
DATA="$GROUP/neo4j_data_v3_ablation${NEO4J_DATA_SUFFIX:-}"  # ISOLATED from neo4j_data_v3 (and from
                                                             # any other concurrent ablation job via
                                                             # NEO4J_DATA_SUFFIX) — other v3 jobs may
                                                             # run at the same time on other nodes.
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

# ── AD probe, weaker-SL ablation, base AD fixed ───────────────────────────────────
SL_ARGS="--adapter_suffix ${SL_ADAPTER_SUFFIX:-_v3}"
if [[ "${NO_SL_ADAPTER:-0}" -eq 1 ]]; then
    SL_ARGS="--no_sl_adapter"
fi
python kaya/ad_probe_v3.py --model_key mistral7b --ad_backend base $SL_ARGS
echo "Finished at $(date)"
