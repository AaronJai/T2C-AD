#!/bin/bash --login
#SBATCH --job-name=t2c_sl_v3
#SBATCH --partition=gpu
#SBATCH --time=1-00:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:2
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.4 — continue-SFT the Schema Linker adapter on POLE v3 + Ozsoy replay (2 epochs,
# initialised from checkpoints/mistral7b/sl_adapter). Writes checkpoints/mistral7b/sl_adapter_v3
# (v2's sl_adapter is untouched). Needs data/pole_sl_train_mixed.jsonl + data/pole_sl_eval.jsonl
# (kaya/73_build_pole_sft_data.slurm). At ~2-4k mixed rows / 2 epochs this is hours, not the
# multi-day 2.1 from-scratch run — a single job suffices (no chaining).
# Submit from repo root: sbatch kaya/74_train_sl_v3.slurm

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

python -m experiments.train_schema_linker --model_key mistral7b \
    --train config/schema_linker_train_v3.yaml
echo "Finished at $(date)"
