#!/bin/bash --login
#SBATCH --job-name=t2c_qwen_fit_test
#SBATCH --partition=gpu
#SBATCH --time=08:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:v100-32gb:2
#SBATCH --mem=96G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.5 — Qwen2.5-32B onboarding + precision fit-test. GO/NO-GO measurement BEFORE 10.6
# spends days of GPU time: how much VRAM the 32B base needs at 4-bit vs 8-bit, whether one
# QLoRA step and one k=5 diverse-beam SL generate fit on a 32GB card, and how long a step takes.
#
# MUST land on a v100-32gb node (k017-020) — `--gres=gpu:v100-32gb:2` above pins that; a 16GB
# V100 cannot hold this model (workflow rules §7). Needs Qwen/Qwen2.5-32B already cached in
# $HF_HOME by the login node (compute nodes are offline — kaya/README.md §Gotchas).
#
# Each phase is a SEPARATE process on purpose: a 4-bit and an 8-bit copy of a 32B base will not
# coexist on one node, and a fresh process guarantees a clean allocator for each measurement.
# The 8-bit leg runs with --tolerate_failure: bitsandbytes LLM.int8() wants sm75+ and Kaya's
# V100s are sm70, so "8-bit does not run here" is itself a valid, recorded result.
#
# Writes results/qwen_fit_test/{load_4bit,load_8bit,generate_4bit,train_4bit,summary}.json.
# After it lands: set load_in_4bit/dtype in the config/models.yaml `qwen2.5-32b` entry to the
# locked choice (already 4-bit/fp16 as the expected outcome) and copy the numbers into the
# 10.5 tracker row.
#
# Submit from repo root: sbatch kaya/97_qwen_fit_test.slurm
#   LOCKED=8bit sbatch kaya/97_qwen_fit_test.slurm   # to run the train/generate legs at 8-bit

set -uo pipefail   # NOT -e: a phase that OOMs must not abort the remaining measurements

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

LOCKED="${LOCKED:-4bit}"
echo "Locked-precision legs (train/generate) will run at: $LOCKED"

# BATCH: override the train leg's per_device_train_batch_size (default: the 10.3 YAML's 2).
#        The first run (job 1100717) OOM'd at batch 2 — Qwen's ~152k-vocab fp32 logits upcast
#        for the loss is 4.06 GiB at seq 3584 × batch 2, which tips the lm_head card over 32 GB
#        even sharded + gradient-checkpointed. Re-run the train leg alone at batch 1 with
#        `BATCH=1 ONLY=train sbatch kaya/97_qwen_fit_test.slurm` (the load/generate fragments
#        from the first run are reused by the summary).
# ONLY:  "train" skips the load/generate legs (their fragments already exist) and runs only the
#        train + summary legs — a cheap re-measure without reloading three more times.
BATCH="${BATCH:-}"
BATCH_FLAG=""
[[ -n "$BATCH" ]] && BATCH_FLAG="--batch_size $BATCH"

if [[ "${ONLY:-}" != "train" ]]; then
    echo; echo "================ [1/5] LOAD @ 4-bit ================"
    python kaya/qwen_fit_test.py --phase load --precision 4bit --tolerate_failure

    echo; echo "================ [2/5] LOAD @ 8-bit ================"
    python kaya/qwen_fit_test.py --phase load --precision 8bit --tolerate_failure

    echo; echo "======== [3/5] DIVERSE-BEAM SL GENERATE (k=5) @ $LOCKED ========"
    python kaya/qwen_fit_test.py --phase generate --precision "$LOCKED" --tolerate_failure
fi

echo; echo "======== [4/5] ONE QLoRA TRAIN STEP @ $LOCKED (batch=${BATCH:-yaml}) ========"
# max_seq_length 3584 comes from config/schema_linker_train_pole_external.yaml; per_device
# batch defaults to that YAML's 2 unless BATCH overrides. Rows are real 10.2 external-POLE SL rows.
python kaya/qwen_fit_test.py --phase train --precision "$LOCKED" $BATCH_FLAG --tolerate_failure

echo; echo "================ [5/5] SUMMARY ================"
python kaya/qwen_fit_test.py --phase summary --precision "$LOCKED"

echo "Finished at $(date)"
