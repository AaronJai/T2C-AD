#!/bin/bash --login
#SBATCH --job-name=t2c_run_evaluation
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
# Step 5.4 — the full end-to-end evaluation: experiments/run_evaluation.py over all 125
# benchmark questions × 3 conditions, producing populated Tables 1–3 (results/tables_mistral7b.md
# + results/metrics_mistral7b.json). Needs BOTH a GPU (base model / SL+QG adapters / AD-Dis LLM /
# sentence-transformers evaluator fallback) AND a live Neo4j (Entity Lookup, CyVer schema/props,
# DB executor, ground-truth execution in the Semantic Evaluator) — so Neo4j runs in the
# BACKGROUND inside this same GPU job (same node → bolt://localhost:7687), per kaya/README.md
# §"Neo4j on Kaya" and ai-workflow-rules.md §7.
# Submit from repo root:  sbatch kaya/65_run_evaluation.slurm
#
# Memory (Tier-1 OOM fix, decisions-log 2026-06-23 5.3/5.4): run_evaluation reads
# load_in_4bit/dtype from the config/models.yaml registry and threads them into all three
# builders, so every 7B loads as 4-bit/fp16 (~4–5 GB each) exactly as it was QLoRA-trained.
# C2 (SL+QG) ≈ 9 GB and C3 (SL+QG+AD) ≈ 14 GB therefore fit a SINGLE 16 GB V100 — gpu:2 is
# requested only as headroom for C3's beam_k=5 KV cache; gpu:1 is sufficient if the queue is busy.
#
# Prerequisites:
#   - kaya/50_neo4j_pull.sh (one-time) + a first Neo4j load (data persists in $MYGROUP/neo4j_data
#     after kaya/55_neo4j.slurm has loaded data/SyntheticPoliceKG.cypher once).
#   - Trained adapters at checkpoints/mistral7b/{sl_adapter,qg_adapter} (Phase 2).
#   - config/schema_linker_inference.yaml carries the locked diversity_penalty (2.2).
#   - config/pipeline.yaml has use_embedding_model: true → the all-MiniLM-L6-v2 sentence-transformer
#     must already be in $HF_HOME (offline mode is on). If it is not cached, either predownload it
#     on the login node or set use_embedding_model: false in config/pipeline.yaml (exact-match only).

set -euo pipefail

module load Anaconda3/2024.06
module load cuda/12.6.3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
# Reduce CUDA allocator fragmentation across the 125-question C3 loop (beam_k=5 KV spikes);
# build_condition3 also pins SL→cuda:0, QG+AD→cuda:1 so the trio uses both V100s (decisions-log 2026-06-26).
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset LD_PRELOAD

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"
nvidia-smi

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

# Same Apptainer flags as 55_neo4j.slurm (--no-mount /opt restores the image JDK;
# --writable-tmpfs lets neo4j write its pid file on the read-only image root).
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

# Wait for bolt to accept the configured password (DB already initialised on a prior run).
for i in $(seq 1 60); do
    if apptainer exec --no-mount /opt "$SIF" \
        cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" \
        >/dev/null 2>&1; then
        echo "Neo4j ready after ${i} checks."
        break
    fi
    sleep 2
done

# ── Run the full evaluation (C1 → C2 → C3 over all 125 questions) ────────────────
python -m experiments.run_evaluation config/pipeline.yaml

echo "Wrote results/tables_mistral7b.md + results/metrics_mistral7b.json"
echo "Finished at $(date)"
