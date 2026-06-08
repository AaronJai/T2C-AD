#!/bin/bash --login
#SBATCH --job-name=t2c_smoke_sl
#SBATCH --partition=ondemand-gpu
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Smoke test for 2.1 SL training at max_seq_length=3584 (raised from 1024 — see decisions-log
# 2026-06-08). Confirms the fp16 QLoRA setup loads and fits in 16 GB *before* committing to
# the full 24h run (10_train_sl.slurm). Targets ondemand-gpu (shorter queue, 12h cap) with a
# short walltime so it self-terminates if you forget to scancel it.
#
# Every training batch is pre-padded to max_seq_length (_JsonlSFTDataset), so peak memory is
# hit on the very FIRST forward/backward pass — if that doesn't OOM, nothing later will either.
# You don't need to wait for a logged loss line (logging_steps=50, i.e. 400 micro-batches);
# a few stable minutes with no "CUDA out of memory" in the .err is enough signal.
#
#   tail -f logs/t2c_smoke_sl_<jobid>.out          # CUDA detected + model loading
#   tail -f logs/t2c_smoke_sl_<jobid>.err          # watch for a CUDA OOM traceback
#   cat  logs/t2c_smoke_sl_<jobid>.gpu.out         # memory.used sampled every 30s — should
#                                                  # stay comfortably under ~16000 MiB
#
# Once satisfied: scancel <jobid>.  (If it times out mid-run, no harm — run_sft only writes
# checkpoints/mistral7b/sl_adapter at the very end, so a partial run leaves it untouched.)
#
# Submit from repo root: sbatch kaya/05_smoke_sl.slurm

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

# Background GPU-memory logger (every 30s), written to its own file so it doesn't interleave
# with training output — gives you durable peak-memory evidence even if you weren't watching live.
nvidia-smi --query-gpu=timestamp,memory.used,memory.total,utilization.gpu \
    --format=csv -l 30 > "logs/${SLURM_JOB_NAME}_${SLURM_JOBID}.gpu.out" &
GPU_LOGGER_PID=$!

python -m experiments.train_schema_linker --model_key mistral7b
EXIT_CODE=$?

kill "$GPU_LOGGER_PID" 2>/dev/null
echo "Finished at $(date) — exit code: $EXIT_CODE"
exit $EXIT_CODE
