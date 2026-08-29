#!/bin/bash --login
#SBATCH --job-name=t2c_qwen72b_fit_test
#SBATCH --partition=rrifcs
#SBATCH --gres=gpu:h100:1
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=200G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 11.2 — Qwen2.5-72B onboarding + H100 throughput fit-test.
#
# This is a CALIBRATION, not a GO/NO-GO. 10.5 had to decide whether a 32B ran at all and at
# what precision; none of that is open here. Same Qwen2ForCausalLM architecture, same loader,
# same 152,064-token vocabulary, same pinned transformers<4.46 — so `load_in_4bit: true`,
# `dtype: float16`, `target_modules: ["q_proj","v_proj"]`, batch 1, grad-accum 32,
# gradient checkpointing and `max_seq_length: 3584` are all INHERITED and are not re-decided
# here (11.2's parity clause: model size must be the only variable across the 7B/32B/72B
# columns). This job only produces numbers.
#
# ONE H100 (93.6 GiB): the 4-bit 72B is predicted at ~41 GiB, so a single card should hold the
# model plus a batch-1 gradient-checkpointed train step. `--gres=gpu:h100:1` also makes the
# measurement honest — with 2+ cards visible, `device_map="auto"` would spread a model that
# fits one card and the "does it fit" answer would be unreadable (10.5 hit exactly that).
#
# Needs Qwen/Qwen2.5-72B cached in $HF_HOME (37 shards / 135.4 GiB — verified by 11.1 and by
# `python kaya/predownload.py --model_key qwen2.5-72b` on the login node). Compute nodes are
# offline (kaya/README.md § Gotchas).
#
# The harness is kaya/qwen_fit_test.py, reused from 10.5 with only additive flags. The 8-bit
# leg is DROPPED (10.5 settled precision; an 8-bit 72B is ~78 GiB and of no interest).
#
# Writes results/qwen72b_fit_test/{load_4bit,generate_4bit,train_4bit,train_4bit_batch2,
# summary}.json — a separate directory from 10.5's results/qwen_fit_test/, which must not be
# overwritten.
#
# Submit from the repo root:  sbatch kaya/111_qwen72b_fit_test.slurm

set -uo pipefail   # NOT -e: a leg that OOMs must not abort the remaining measurements

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

MODEL_KEY=qwen2.5-72b
RESULTS_DIR=results/qwen72b_fit_test
# The Qwen train YAML 11.3 will actually use — batch 1, grad-accum 32, GC on, seq 3584, fp16.
# (10.5 read the Mistral YAML and had to override its batch 2; the parity clause fixes batch 1,
# so read the recipe from the file that states it rather than from a flag.)
TRAIN_CONFIG=config/schema_linker_train_qwen_pole_external.yaml
COMMON="--model_key $MODEL_KEY --results_dir $RESULTS_DIR --precision 4bit"

echo; echo "========== [1/5] LOAD @ 4-bit (build_llm, no loader change) =========="
# Acceptance 1 + leg 1: the 4-bit footprint on ONE H100. 11.4's device planning depends on
# this number more than on anything else in the job.
python kaya/qwen_fit_test.py --phase load $COMMON --tolerate_failure

echo; echo "========== [2/5] DIVERSE-BEAM SL GENERATE (k=5) @ 4-bit =========="
# Leg 4: the live 3.1 decoding path. 10.7 measured ~7 s/item at 32B on an H100; this sets
# 11.4's G1/G4 wall-clock budget.
python kaya/qwen_fit_test.py --phase generate $COMMON --tolerate_failure

echo; echo "========== [3/5] QLoRA TRAIN STEP @ batch 1 + GC =========="
# Leg 2 — the headline number: peak VRAM and s/micro-step at the LOCKED recipe. 11.3's budget
# table is rebuilt from it (its ~6.8 s is a parameter-scaled estimate, not a measurement).
# --no_plain_leg: the no-gradient-checkpointing question was 10.5's and is settled — 10.6 added
# the `gradient_checkpointing` flag to run_sft and every Phase-11 YAML sets it true.
python kaya/qwen_fit_test.py --phase train $COMMON \
    --train_config "$TRAIN_CONFIG" --no_plain_leg --tolerate_failure

echo; echo "========== [4/5] BATCH-2 HEADROOM PROBE (evidence only) =========="
# Leg 3: recorded so the writeup can say batch 1 was a parity CHOICE, not a hardware limit.
# --tolerate_failure because an OOM here is a valid result; --tag keeps it from overwriting
# the batch-1 fragment. NOT adopted whatever it says.
python kaya/qwen_fit_test.py --phase train $COMMON \
    --train_config "$TRAIN_CONFIG" --batch_size 2 --tag batch2 --no_plain_leg --tolerate_failure

echo; echo "========== [5/5] SUMMARY (legs 5 + 6) =========="
# --budget_profile phase11: extrapolate over 11.3's real recipe (Stage-1 generic on the 4k
# Ozsoy sample, 3 epochs; four POLE-only continues, 2 epochs) — NOT 10.5's _mixed-file
# assumption. The co-located-load arithmetic (leg 5) sizes 11.4's --gres.
python kaya/qwen_fit_test.py --phase summary $COMMON --budget_profile phase11

echo "Finished at $(date)"
