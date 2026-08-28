#!/bin/bash --login
#SBATCH --job-name=t2c_qwen_cov
#SBATCH --partition=rrifcs
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100:1
#SBATCH --mem=64G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.6 acceptance criterion 4 — quick intrinsic Cov@5 (~25 items) per substrate with the
# newly trained Qwen SL adapters, a fast read before 10.7's full G1. Reuses the existing 7.4/10.3
# cov-check harnesses unchanged (both already take --model_key); nothing here is Qwen-specific
# beyond that flag, and no config is edited.
#
#   SUBSTRATE=v3            -> kaya/sl_v3_cov_check.py           (checkpoints/qwen2.5-32b/sl_adapter_v3)
#   SUBSTRATE=pole_external -> kaya/sl_pole_external_cov_check.py (…/sl_adapter_pole_external)
#
# config/schema_linker_inference.yaml has no `decoding[qwen2.5-32b]` entry — that belongs to 10.7,
# which locks it. Both harnesses fall back to {strategy: beam, diversity_penalty: 1.0, k: 5} (the
# file's flat default), the same v3-locked penalty 10.3/10.4 reused for Mistral on this substrate.
#
#   sbatch --export=ALL,SUBSTRATE=v3 kaya/103_qwen_cov_check.slurm
# Runs on the H100 partition (see 101/102 headers); for a v100-32gb node use
#   sbatch --partition=gpu --gres=gpu:v100-32gb:2 --export=ALL,SUBSTRATE=v3 kaya/103_qwen_cov_check.slurm

set -uo pipefail
SUBSTRATE="${SUBSTRATE:-v3}"
case "$SUBSTRATE" in
    v3)            SCRIPT=kaya/sl_v3_cov_check.py ;;
    pole_external) SCRIPT=kaya/sl_pole_external_cov_check.py ;;
    *) echo "Unknown SUBSTRATE '$SUBSTRATE' (v3|pole_external)" >&2; exit 1 ;;
esac

module load Anaconda3/2024.06
module load cuda/12.6.3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
unset LD_PRELOAD

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date) — substrate=$SUBSTRATE, script=$SCRIPT"
nvidia-smi

python "$SCRIPT" --model_key qwen2.5-32b
echo "Finished at $(date)"
