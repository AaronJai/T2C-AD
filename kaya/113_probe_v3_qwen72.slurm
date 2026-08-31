#!/bin/bash --login
#SBATCH --job-name=t2c_probe_v3_qwen72
#SBATCH --partition=rrifcs
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100:1
#SBATCH --mem=64G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 11.4 — Gate G2 (part 2): the 2.3 entropy probe for Qwen2.5-72B on the v3 substrate.
# Reads the decoding block locked by the sweep (112), reuses the cached
# results/beams_qwen2.5-72b_v3.jsonl written by 11.3's G1 run (kaya/104, job 1148276) when it
# already reflects that decoding (GPU-free rescore), and reports the entropy->ambiguity AUC
# against the ~0.62 general-model baseline (project-overview criterion #6). Writes
# results/entropy_probe_qwen2.5-72b_v3.json.
#
# WHY THIS NUMBER MATTERS AS A SCALING DATA POINT: the 7B post-SFT probe and 10.7's 32B run
# (AUC 0.570) both fell short of criterion #6's 0.62 bar, and 10.7 recorded that scaling the base
# 4.6x did not rescue the SECONDARY signal. This is the third scale point on that null. Report it
# whichever way it falls — a second null strengthens project-overview 7's LLM-primary decision.
#
# RUN 112_sweep_v3_qwen72.slurm FIRST. If the sweep re-locked a DIFFERENT penalty than the one the
# beam cache was generated at (11.3 generated it at dp=1.0), the cache is stale — set REGEN=1 to
# regenerate at the locked value:
#   REGEN=1 sbatch kaya/113_probe_v3_qwen72.slurm
# (The 112 log prints the before -> after penalty, so this is a one-line check.) A regenerate is
# 120 items x 11.2's measured 29.6 s = ~1 h, which is why the walltime is 6 h rather than the
# minutes a cache rescore takes.
#
# v3 only, for the same CLI reason as the sweep (--dataset_version accepts v2|v3); the external
# substrate's probe stays deferred exactly as 10.4/10.7 deferred it (decisions-log 2026-08-22).
# Submit from repo root:  sbatch kaya/113_probe_v3_qwen72.slurm

set -euo pipefail

MODEL_KEY="${MODEL_KEY:-qwen2.5-72b}"

module load Anaconda3/2024.06
module load cuda/12.6.3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset LD_PRELOAD

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"
nvidia-smi

REGEN_FLAG=""
if [[ "${REGEN:-0}" -eq 1 ]]; then
    REGEN_FLAG="--regenerate"
    echo "REGEN=1 — regenerating beams at the locked v3 decoding."
fi

python -m experiments.entropy_probe \
    --model_key "$MODEL_KEY" \
    --benchmark data/benchmark-v3.json \
    --dataset_version v3 \
    --results_tag v3 \
    $REGEN_FLAG
echo "Finished at $(date)"
