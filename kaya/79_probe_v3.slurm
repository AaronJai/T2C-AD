#!/bin/bash --login
#SBATCH --job-name=t2c_probe_v3
#SBATCH --partition=gpu
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.5 — Gate G2 (part 2): 2.3 entropy probe on the v3 substrate. Reads the decoding
# block re-locked by the sweep (78), reuses the cached results/beams_mistral7b_v3.jsonl when it
# already reflects that decoding (GPU-free rescore), and reports the entropy→ambiguity AUC vs
# the ~0.62 baseline (criterion #6: > 0.62). Writes results/entropy_probe_mistral7b_v3.json.
#
# RUN 78_sweep_v3.slurm FIRST. If the sweep re-locked a DIFFERENT penalty than G1's cache was
# generated at, set REGEN=1 so the probe regenerates beams at the locked decoding:
#   REGEN=1 sbatch kaya/79_probe_v3.slurm
# Submit from repo root: sbatch kaya/79_probe_v3.slurm

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

REGEN_FLAG=""
if [[ "${REGEN:-0}" -eq 1 ]]; then
    REGEN_FLAG="--regenerate"
    echo "REGEN=1 — regenerating beams at the locked v3 decoding."
fi

python -m experiments.entropy_probe \
    --model_key mistral7b \
    --benchmark data/benchmark-v3.json \
    --dataset_version v3 \
    --results_tag v3 \
    $REGEN_FLAG
echo "Finished at $(date)"
