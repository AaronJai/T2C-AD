#!/bin/bash --login
#SBATCH --job-name=t2c_sl_pole_external_cov
#SBATCH --partition=ondemand-gpu
#SBATCH --time=01:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.3 — acceptance criterion 3: quick intrinsic Cov@5 check of sl_adapter_pole_external
# against a ~25-item external-POLE benchmark sample. GPU only, no Neo4j (schema linking alone).
# The fast sanity read before 10.4's full gated E2E run. Submit from repo root:
# sbatch kaya/96_sl_pole_external_cov_check.slurm

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

python kaya/sl_pole_external_cov_check.py --model_key mistral7b
echo "Finished at $(date)"
