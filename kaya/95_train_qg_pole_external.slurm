#!/bin/bash --login
#SBATCH --job-name=t2c_qg_pole_external
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
# Step 10.3 — continue-SFT the Query Generator adapter on external-POLE + Ozsoy replay (2 epochs,
# initialised from checkpoints/mistral7b/qg_adapter). Writes
# checkpoints/mistral7b/qg_adapter_pole_external (v2's qg_adapter and v3's qg_adapter_v3 are
# untouched). Needs data/pole_ext_qg_train_mixed.jsonl + data/pole_ext_qg_eval.jsonl (10.2).
# Independent of 94_train_sl_pole_external.slurm — can run in parallel. run_sft's
# resume-from-checkpoint + skip-if-saved (2.1) handle a re-queue if the job is pre-empted.
# Submit from repo root: sbatch kaya/95_train_qg_pole_external.slurm

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
    --train config/query_generator_train_pole_external.yaml
echo "Finished at $(date)"
