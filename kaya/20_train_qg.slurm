#!/bin/bash --login
#SBATCH --job-name=t2c_qg
#SBATCH --partition=gpu
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 2.4 — Query Generator LoRA/QLoRA adapter (3 epochs, fp16 on V100).
# Writes checkpoints/mistral7b/qg_adapter. Independent of the sweep/probe — can run in
# parallel with 10_train_sl.slurm.  Submit from repo root: sbatch kaya/20_train_qg.slurm

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
python -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0))"

python -m experiments.train_query_generator --model_key mistral7b
echo "Finished at $(date)"
