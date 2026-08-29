#!/bin/bash --login
#SBATCH --job-name=t2c_g1_cov_qwen
#SBATCH --partition=rrifcs
#SBATCH --time=03:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100:1
#SBATCH --mem=64G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.7 — Gate G1 (the linchpin) for Qwen2.5-32B, AND the cheap intrinsic tier of the
# three-way adapter attribution. GPU only, no Neo4j (schema linking alone).
#
# Two knobs, both defaulted so a bare submit is the headline gate:
#   SUBSTRATE = v3 | pole_external      which benchmark/schema/adapter family
#   TIER      = indomain | generic | noadapter
#       indomain  (default) checkpoints/qwen2.5-32b/sl_adapter_{v3,pole_external}  <- 10.6 Stage 2
#       generic   checkpoints/qwen2.5-32b/sl_adapter                               <- 10.6 Stage 1 (Ozsoy-only)
#       noadapter raw Qwen/Qwen2.5-32B base, no PEFT at all
#   The three tiers ARE the "no adapter / +generic Ozsoy / +generic+POLE" attribution the 10.7
#   spec asks for (cheap tier: intrinsic Cov@5, minutes-scale — not a full e2e). Only the
#   indomain tier writes the headline artefact names; the other two carry a distinct
#   `_qwen_{generic,noadapter}` tag so nothing overwrites the gate result.
#
# Gate rule (7.5/10.4): PROCEED to G2 if Cov@5 >= 0.60; below 0.60 STOP and loop back to 10.6
# (more data/epochs) and document it. Target >= 0.85. 10.6's 25-item samples were v3 0.880 /
# external 0.760 at dp=1.0 — this is the full-benchmark measurement (120 / 100 items).
#
# Runs on the H100 `rrifcs` partition (node k172, 4x H100 NVL 93.6 GiB; needs `rrifcs-users`).
# One card holds the 20.2 GiB 4-bit load measured by the 10.5 fit-test with room to spare.
# For a v100-32gb node instead:  sbatch --partition=gpu --gres=gpu:v100-32gb:1 ...
#
#   sbatch --export=ALL,SUBSTRATE=v3            kaya/104_g1_coverage_qwen.slurm
#   sbatch --export=ALL,SUBSTRATE=pole_external kaya/104_g1_coverage_qwen.slurm
#   sbatch --export=ALL,SUBSTRATE=v3,TIER=generic   kaya/104_g1_coverage_qwen.slurm
#   sbatch --export=ALL,SUBSTRATE=v3,TIER=noadapter kaya/104_g1_coverage_qwen.slurm
# Submit from repo root.

set -euo pipefail

SUBSTRATE="${SUBSTRATE:-v3}"
TIER="${TIER:-indomain}"
MODEL_KEY="${MODEL_KEY:-qwen2.5-32b}"

case "$SUBSTRATE" in
    v3)            SCRIPT=kaya/g1_sl_coverage_v3.py;            SUFFIX="_v3" ;;
    pole_external) SCRIPT=kaya/g1_sl_coverage_pole_external.py; SUFFIX="_pole_external" ;;
    *) echo "Unknown SUBSTRATE '$SUBSTRATE' (v3|pole_external)" >&2; exit 1 ;;
esac

# TIER -> adapter selection + artefact tag. The default tier writes the harnesses' own default
# filenames (results/g1_sl_coverage_{model_key}{_substrate}.json), i.e. the headline gate result.
case "$TIER" in
    indomain)  TIER_ARGS=(--adapter_suffix "$SUFFIX"); TAG="" ;;
    generic)   TIER_ARGS=(--adapter_suffix "");        TAG="_qwen_generic" ;;
    noadapter) TIER_ARGS=(--no_adapter);               TAG="_qwen_noadapter" ;;
    *) echo "Unknown TIER '$TIER' (indomain|generic|noadapter)" >&2; exit 1 ;;
esac

RESULTS="results/g1_sl_coverage_${MODEL_KEY}${SUFFIX}${TAG}.json"
BEAMS="results/beams_${MODEL_KEY}${SUFFIX}${TAG}.jsonl"

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
echo "  substrate=$SUBSTRATE  tier=$TIER  model_key=$MODEL_KEY  script=$SCRIPT"
echo "  -> $RESULTS   (beams: $BEAMS)"
nvidia-smi

python "$SCRIPT" --model_key "$MODEL_KEY" "${TIER_ARGS[@]}" \
    --results "$RESULTS" --beam_cache "$BEAMS"
echo "Finished at $(date)"
