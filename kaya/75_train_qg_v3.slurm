#!/bin/bash --login
#SBATCH --job-name=t2c_qg_v3
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
# Step 7.4 — continue-SFT the Query Generator adapter on POLE v3 + Ozsoy replay (2 epochs,
# initialised from checkpoints/mistral7b/qg_adapter). Writes checkpoints/mistral7b/qg_adapter_v3
# (v2's qg_adapter is untouched). Needs data/pole_qg_train_mixed.jsonl + data/pole_qg_eval.jsonl
# (kaya/73_build_pole_sft_data.slurm). Independent of 74_train_sl_v3.slurm — can run in parallel.
# Submit from repo root: sbatch kaya/75_train_qg_v3.slurm

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

python -m experiments.train_query_generator --model_key mistral7b \
    --train config/query_generator_train_v3.yaml
echo "Finished at $(date)"
