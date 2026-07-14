#!/bin/bash --login
#SBATCH --job-name=t2c_g1_cov_api_v3
#SBATCH --partition=work
#SBATCH --time=03:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 8.3 — Gate G1 (API): full 120-item intrinsic Cov@5 / EM@1 for the `kind: api` Schema
# Linker (temperature sampling k=5, instruct prompt). The API sibling of kaya/77_g1_coverage_v3
# — NO GPU, NO Neo4j (schema linking alone), `--partition=work`, no `--gres`. G1 runs BEFORE G2
# re-locks the temperature, so the SL decodes at the pre-sweep default temperature 0.7 (mirrors
# 7.5's pre-sweep dp=0.2). PROCEED to G2 only if Cov@5 >= 0.60.
# Caches results/beams_claude-sonnet_v3.jsonl so G2's probe (kaya/84) rescores it GPU-free.
# Submit from repo root (export the key FIRST):
#   ANTHROPIC_API_KEY=... sbatch kaya/83_g1_coverage_api_v3.slurm

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

# Pre-sweep decoding (temperature 0.7, k=5, instruct prompt) is g1_sl_coverage_v3.py's default
# for an `kind: api` model; pass --decoding to override.
python kaya/g1_sl_coverage_v3.py --model_key "${MODEL_KEY:-claude-sonnet}"
echo "Finished at $(date)"
