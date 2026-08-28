#!/bin/bash --login
#SBATCH --job-name=t2c_qwen_sl
#SBATCH --partition=gpu
#SBATCH --time=3-00:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:v100-32gb:2
#SBATCH --mem=96G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.6 — Qwen2.5-32B SCHEMA LINKER adapter DAG (two-stage, mirroring how Mistral was
# trained). One file, three jobs:
#
#   generic  (~50 h)  from-scratch LoRA on the 4k Ozsoy SL sample -> checkpoints/qwen2.5-32b/sl_adapter
#     |-- v3            (~15 h)  continue-SFT on POLE v3       -> .../sl_adapter_v3
#     `-- pole_external (~17 h)  continue-SFT on external POLE -> .../sl_adapter_pole_external
#
# Both continues are submitted with --dependency=afterok:<generic> at submit time, so they only
# start once the generic adapter exists. Every job is under Kaya's 72 h cap — no chaining.
# 102_train_qwen_qg.slurm is the identical DAG for the Query Generator and runs in parallel.
#
# SUBMIT THE WHOLE DAG (from the repo root, on the login node):
#     bash kaya/101_train_qwen_sl.slurm
# SUBMIT ONE STAGE ONLY (e.g. to re-run a continue after fixing something):
#     sbatch --time=1-00:00:00 --export=ALL,STAGE=v3 kaya/101_train_qwen_sl.slurm
# Plain `sbatch kaya/101_train_qwen_sl.slurm` runs the generic stage alone (STAGE defaults to it).
#
#
#
# H100 OPTION (`rrifcs` partition, added 2026-08-28 — needs membership of the `rrifcs-users` unix
# group). Node k172 has 4x H100 NVL (93.6 GiB each), so ONE GPU holds the whole 43.5 GiB training
# footprint and two stages can run side by side. Measured 3.03 s/micro-step vs 3.03->13.98 s on a
# V100 (4.6x faster). Override on the command line — no edit to this file is needed:
#     sbatch --partition=rrifcs --gres=gpu:h100:1 --time=12:00:00 --mem=64G \
#            --export=ALL,STAGE=v3 kaya/101_train_qwen_sl.slurm
# Keep fp16 as the YAMLs set it (do NOT switch to bf16 on sm90) so all six adapters share one recipe.
# Wall-clock: the generic stage is ~49.7 h of optimiser steps (4000 rows x 3 epochs at the
# measured 14.9 s/step) PLUS three full Ozsoy eval passes, so it is budgeted at the gpu
# partition's 72 h cap rather than 50 h. If it ever does hit the cap, `save_strategy: epoch`
# + run_sft's resume-from-checkpoint mean re-submitting the same stage picks up from the last
# completed epoch (2.1) — and the continues, gated on afterok, simply stay queued until it
# succeeds.
# --gres=gpu:v100-32gb:2 is REQUIRED (k017-k020): a 16 GB V100 cannot hold this model, and
# training peaks at 25.3 GiB on one card / 43.5 GiB total with device_map="auto" sharding
# (10.5 fit-test, job 1101258). The YAMLs pin batch 1 + accum 32 + gradient checkpointing —
# without those this OOMs at step 0. Needs Qwen/Qwen2.5-32B cached in $HF_HOME (compute nodes
# are offline) and, for the generic stage, data/ozsoy_sl_train_4k.jsonl
# (`python -m experiments.sample_ozsoy_subset --split sl`).

set -uo pipefail

# ── Submit path: not running under Slurm -> submit the three-job DAG and exit. ───────────
if [[ -z "${SLURM_JOB_ID:-}" ]]; then
    cd "$(dirname "$0")/.." || exit 1
    if [[ ! -s data/ozsoy_sl_train_4k.jsonl ]]; then
        echo "ERROR: data/ozsoy_sl_train_4k.jsonl is missing." >&2
        echo "  Run: python -m experiments.sample_ozsoy_subset --split sl" >&2
        exit 1
    fi
    GENERIC_ID=$(sbatch --parsable --job-name=t2c_qwen_sl_generic \
        --export=ALL,STAGE=generic "$0") || exit 1
    echo "generic        -> job $GENERIC_ID (~50 h)"
    for STAGE in v3 pole_external; do
        DEP_ID=$(sbatch --parsable --job-name="t2c_qwen_sl_$STAGE" --time=1-00:00:00 \
            --dependency="afterok:$GENERIC_ID" --export=ALL,STAGE="$STAGE" "$0") || exit 1
        echo "$STAGE (afterok:$GENERIC_ID) -> job $DEP_ID (~15-17 h)"
    done
    exit 0
fi

# ── Job path: train the one stage named by $STAGE. ──────────────────────────────────────
STAGE="${STAGE:-generic}"
case "$STAGE" in
    generic)       TRAIN_YAML=config/schema_linker_train_qwen_generic.yaml ;;
    v3)            TRAIN_YAML=config/schema_linker_train_qwen_v3.yaml ;;
    pole_external) TRAIN_YAML=config/schema_linker_train_qwen_pole_external.yaml ;;
    *) echo "Unknown STAGE '$STAGE' (generic|v3|pole_external)" >&2; exit 1 ;;
esac

module load Anaconda3/2024.06
module load cuda/12.6.3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
unset LD_PRELOAD

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date) — stage=$STAGE, train=$TRAIN_YAML"
nvidia-smi

# run_sft's skip-if-saved + resume-from-checkpoint (2.1) make a re-queue safe.
python -m experiments.train_schema_linker --model_key qwen2.5-32b --train "$TRAIN_YAML"
echo "Finished at $(date)"
