#!/bin/bash --login
#SBATCH --job-name=t2c_sweep
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
# Step 2.2 — diversity_penalty sweep over the 125-q POLE benchmark using the SL adapter.
# Requires 10_train_sl.slurm to have finished (reads checkpoints/mistral7b/sl_adapter).
# Writes config/schema_linker_inference.yaml (locked penalty) + results/diversity_penalty_sweep.json.
# Submit from repo root: sbatch kaya/30_sweep.slurm

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

python -m experiments.diversity_penalty_sweep --model_key mistral7b
echo "Finished at $(date)"
