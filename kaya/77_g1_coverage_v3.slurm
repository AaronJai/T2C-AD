#!/bin/bash --login
#SBATCH --job-name=t2c_g1_cov_v3
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
# Step 7.5 — Gate G1 (the linchpin): full 120-item intrinsic Cov@5 / EM@1 of sl_adapter_v3.
# GPU only, no Neo4j (schema linking alone). PROCEED to G2 only if Cov@5 >= 0.60.
# Caches results/beams_mistral7b_v3.jsonl so G2's probe reuses the beams GPU-free.
# Submit from repo root: sbatch kaya/77_g1_coverage_v3.slurm

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

python kaya/g1_sl_coverage_v3.py --model_key mistral7b
echo "Finished at $(date)"
