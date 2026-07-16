#!/bin/bash --login
#SBATCH --job-name=t2c_api_smoke_v3_qgfix
#SBATCH --partition=work
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# 8.3 follow-up (decisions-log 2026-07-16) — G0.5 re-run to verify the QG include_properties /
# few-shot fix (build_qg_prompt_api) before committing to a full G4 re-run. Same as
# 82_api_smoke_v3.slurm, just writing to a distinct report path so the original post-fix
# evidence (results/api_smoke_claude-sonnet_v3.txt, job 1055754) is never overwritten.
# Submit from repo root (export the key FIRST):
#   ANTHROPIC_API_KEY=... sbatch kaya/89_api_smoke_v3_qgfix.slurm

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

python kaya/api_smoke_v3.py --model_key "${MODEL_KEY:-claude-sonnet}" --n_questions "${N_QUESTIONS:-6}" \
    --report results/api_smoke_claude-sonnet_v3-qgfix.txt
echo "Finished at $(date)"
