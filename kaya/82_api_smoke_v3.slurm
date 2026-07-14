#!/bin/bash --login
#SBATCH --job-name=t2c_api_smoke_v3
#SBATCH --partition=work
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 8.3 — Gate G0.5: Claude API smoke over a stratified handful of v3 questions, the cheap
# pre-flight before the G1–G4 chain. Drives one round-trip through each stage (SL sampling k=5
# instruct, one AD, one Dis, one QG committed + zero-shot) on the `kind: api` model and writes a
# plain-text report of RAW completions vs parsed patterns / Cypher / JSON, plus an egress check
# and a count_tokens measurement of the SL and AD/Dis prompt prefixes (prompt-caching viability).
#
# NO GPU, NO Neo4j (AD/Dis use an empty EntityLookupResult; entity resolution is G3/G4's job).
# `--partition=work`, no `--gres`; needs an API key exported (guard below), as kaya/67.
# Submit from repo root (export the key FIRST):
#   ANTHROPIC_API_KEY=... sbatch kaya/82_api_smoke_v3.slurm

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

python kaya/api_smoke_v3.py --model_key "${MODEL_KEY:-claude-sonnet}" --n_questions "${N_QUESTIONS:-6}"
echo "Finished at $(date)"
