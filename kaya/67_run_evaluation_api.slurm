#!/bin/bash --login
#SBATCH --job-name=t2c_run_eval_api
#SBATCH --partition=work
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 5.5 — the full end-to-end evaluation on an API model (config/models.yaml `kind: api`,
# e.g. active_model: claude-sonnet / gpt-4o). One model runs every stage; the SL gets its
# candidate distribution by TEMPERATURE SAMPLING, not diverse beam search — so NO GPU is needed.
# A live Neo4j IS still required (Entity Lookup, CyVer schema/props, DB executor, ground-truth
# execution in the Semantic Evaluator), so Neo4j runs in the BACKGROUND inside this same job
# (same node → bolt://localhost:7687), exactly as kaya/65_run_evaluation.slurm does.
# Submit from repo root:  sbatch kaya/67_run_evaluation_api.slurm
#
# This is the GPU-free sibling of 65: `--partition=work` + no `--gres=gpu` (set active_model to a
# local key and use 65 instead if you want the fine-tuned Mistral path). Outputs land at
# results/tables_{active_model}.md + results/metrics_{active_model}.json.
#
# Prerequisites:
#   - An API key exported in the submitting shell: ANTHROPIC_API_KEY (Anthropic) or
#     OPENAI_API_KEY (OpenAI). `sbatch` inherits the environment, so `export …` before submitting.
#   - config/pipeline.yaml `active_model` set to an `kind: api` registry entry.
#   - config/schema_linker_inference.yaml carries decoding[<active_model>] with a locked
#     sampling temperature (run experiments/diversity_penalty_sweep.py --model_key <key> first).
#   - kaya/55_neo4j.slurm has loaded the KG once (data persists in $MYGROUP/neo4j_data).
#   - config/pipeline.yaml use_embedding_model: the all-MiniLM-L6-v2 model must be cached in
#     $HF_HOME (offline), or set use_embedding_model: false (exact-match evaluator only).

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

# ── Neo4j in the background (same node → bolt://localhost:7687) ──────────────────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi
if [[ ! -d "$DATA/data/databases" ]]; then
    echo "Neo4j volume $DATA not initialised — run kaya/55_neo4j.slurm once first to load the KG." >&2
    exit 1
fi

APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins")
apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j console &
NEO4J_PID=$!
cleanup() {
    echo "Stopping neo4j (pid $NEO4J_PID) at $(date)"
    kill "$NEO4J_PID" 2>/dev/null || true
    wait "$NEO4J_PID" 2>/dev/null || true
}
trap cleanup EXIT

for i in $(seq 1 60); do
    if apptainer exec --no-mount /opt "$SIF" \
        cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" \
        >/dev/null 2>&1; then
        echo "Neo4j ready after ${i} checks."
        break
    fi
    sleep 2
done

# ── Run the full evaluation (C1 → C2 → C3 over all 125 questions, via API) ────────
python -m experiments.run_evaluation config/pipeline.yaml

echo "Wrote results/tables_<active_model>.md + results/metrics_<active_model>.json"
echo "Finished at $(date)"
