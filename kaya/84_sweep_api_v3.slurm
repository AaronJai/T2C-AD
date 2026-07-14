#!/bin/bash --login
#SBATCH --job-name=t2c_sweep_api_v3
#SBATCH --partition=work
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 8.3 — Gate G2 (API): the work-partition sibling of kaya/78_sweep_v3.slurm. Runs the
# TEMPERATURE sweep (temperature ∈ {0.3,0.7,1.0}, no top_p — Claude 4.x rejects temperature+top_p)
# over all 120 v3 questions with the `kind: api` Schema Linker, and RE-LOCKS decoding[claude-sonnet]
# in config/schema_linker_inference.yaml. NO GPU, NO Neo4j; needs an API key exported (the sweep
# makes live API calls).
#
# The 2.3 entropy-probe rescore then runs CPU-only from the model-keyed beam cache written by
# G1 (kaya/83 → results/beams_claude-sonnet_v3.jsonl); entropy_probe auto-loads that cache when it
# exists, so no beams are regenerated and the probe needs no API key. Run G1 (83) BEFORE this.
# Submit from repo root (export the key FIRST):
#   ANTHROPIC_API_KEY=... sbatch kaya/84_sweep_api_v3.slurm

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

MODEL_KEY="${MODEL_KEY:-claude-sonnet}"

# ── G2a: temperature sweep (re-locks decoding[<model_key>]) ───────────────────────────
python -m experiments.diversity_penalty_sweep \
    --model_key "$MODEL_KEY" \
    --benchmark data/benchmark-v3.json \
    --dataset_version v3 \
    --results_tag v3

# ── G2b: 2.3 entropy-probe rescore, CPU-only from G1's cached beams ───────────────────
if [[ ! -f "results/beams_${MODEL_KEY}_v3.jsonl" ]]; then
    echo "Missing results/beams_${MODEL_KEY}_v3.jsonl — run kaya/83_g1_coverage_api_v3.slurm first." >&2
    exit 1
fi
python -m experiments.entropy_probe \
    --model_key "$MODEL_KEY" \
    --benchmark data/benchmark-v3.json \
    --dataset_version v3 \
    --results_tag v3

echo "Finished at $(date)"
