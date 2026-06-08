#!/bin/bash --login
#SBATCH --job-name=t2c_probe
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
# Step 2.3 — entropy probe over the 125-q POLE benchmark (AUC table vs ~0.62 baseline).
# Requires the SL adapter (2.1) AND the locked penalty in config/schema_linker_inference.yaml (2.2).
# Writes results/entropy_probe_pole.json (+ caches results/beams_pole.jsonl).
# Submit from repo root: sbatch kaya/40_probe.slurm

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

python -m experiments.entropy_probe --model_key mistral7b
echo "Finished at $(date)"
