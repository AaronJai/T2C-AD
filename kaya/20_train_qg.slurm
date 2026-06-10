#!/bin/bash --login
#SBATCH --job-name=t2c_qg
#SBATCH --partition=gpu
#SBATCH --time=3-00:00:00
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
# parallel with 10_train_sl.slurm.
#
# At the ~126s/optimizer-step rate the 05 smoke test measured on Kaya's V100, QG's 3030
# steps need ~106h — more than even the `gpu` partition's 3-day (72h) cap, so one job
# cannot finish it (see decisions-log 2026-06-08, "QG runtime exceeds the 72h cap").
# `pipeline.sft.run_sft` now resumes from the last `save_strategy: epoch` checkpoint in
# output_dir, and is a no-op (returns immediately) if `adapter_model.safetensors` is
# already there — so chain two jobs with a SLURM dependency, e.g.:
#
#   JOB1=$(sbatch --parsable kaya/20_train_qg.slurm)
#   sbatch --dependency=afterany:$JOB1 kaya/20_train_qg.slurm
#
# Job 2 starts only once job 1 ends — by completion or time limit, either way — and either
# resumes mid-training from job 1's last epoch checkpoint, or, if job 1 already finished
# (e.g. the rate runs faster than estimated), exits immediately as a no-op.
#
# Submit from repo root: sbatch kaya/20_train_qg.slurm

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
