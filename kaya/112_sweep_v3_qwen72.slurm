#!/bin/bash --login
#SBATCH --job-name=t2c_sweep_v3_qwen72
#SBATCH --partition=rrifcs
#SBATCH --time=10:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100:1
#SBATCH --mem=64G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 11.4 — Gate G2 (part 1): the 2.2 diversity-penalty sweep for Qwen2.5-72B on the v3
# substrate. Re-scans diversity_penalty over all 120 v3 questions with sl_adapter_v3 (11.3) and
# LOCKS decoding[qwen2.5-72b] in config/schema_linker_inference.yaml. Writes
# results/diversity_penalty_sweep_qwen2.5-72b_v3.json. Run kaya/113_probe_v3_qwen72.slurm AFTER.
#
# WHY v3 ONLY: experiments/diversity_penalty_sweep.py's --dataset_version accepts v2|v3 only, so
# the external substrate cannot be swept without a CLI change that is out of this step's scope —
# the same deferral 10.4 recorded for Mistral and 10.7 for the 32B (decisions-log 2026-08-22 /
# 2026-08-29). The external 72B run therefore REUSES whatever this sweep locks, as a documented
# pragmatic default; 11.3's full-100 external Cov@5 = 0.750 at dp=1.0 says that substrate is not
# decoding-limited.
#
# CONFIG CONTAINMENT (10.7's discipline, kept verbatim): the sweep's write_inference_config()
# rewrites the whole YAML — it preserves other models' `decoding` blocks but drops the file's
# hand-written comments and refreshes the legacy flat `diversity_penalty` mirror to whatever THIS
# model locked. So the sweep writes to a SCRATCH copy and only the chosen decoding[qwen2.5-72b]
# block is merged back into the real file; the mistral7b / qwen2.5-32b / claude-sonnet blocks and
# the flat mirror are then asserted byte-unchanged.
#
# WALLTIME: 3 penalties x 120 items at 11.2 leg 4's MEASURED 29.6 s per k=5 SL decode on one
# H100 NVL = ~3.0 h of generation plus a ~4 min 4-bit load, so 10 h carries ample margin. (10.7's
# 32B sweep took 19m57s at ~7 s/item; the 4.2x per-decode ratio is the sizing rule 11.2 handed
# this step.) One card holds the 11.2-measured 42.5 GiB 4-bit load with 50 GiB to spare.
#
# Runs on the H100 `rrifcs` partition (node k172; needs `rrifcs-users`).
# Submit from repo root:  sbatch kaya/112_sweep_v3_qwen72.slurm

set -euo pipefail

MODEL_KEY="${MODEL_KEY:-qwen2.5-72b}"
REAL_SLI=config/schema_linker_inference.yaml
SCRATCH_SLI=config/.schema_linker_inference.qwen72_sweep.yaml

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

cp "$REAL_SLI" "$SCRATCH_SLI"

python -m experiments.diversity_penalty_sweep \
    --model_key "$MODEL_KEY" \
    --benchmark data/benchmark-v3.json \
    --dataset_version v3 \
    --results_tag v3 \
    --inference_config "$SCRATCH_SLI"

# ── Merge ONLY decoding[qwen2.5-72b] back into the real config; assert nothing else moved ──
python - "$REAL_SLI" "$SCRATCH_SLI" "$MODEL_KEY" <<'PY'
import pathlib, re, sys, yaml

real_p, scratch_p, key = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
real_text = real_p.read_text(encoding="utf-8")
real, scratch = yaml.safe_load(real_text), yaml.safe_load(scratch_p.read_text(encoding="utf-8"))

chosen = scratch["decoding"][key]
before = real["decoding"][key]
print(f"swept decoding[{key}]: {before}  ->  {chosen}")

# Rewrite the model's block in place, preserving every comment and every other entry.
block = "".join(f"    {k}: {v}\n" for k, v in chosen.items())
pattern = re.compile(rf"(^  {re.escape(key)}:\n)(?:    \S.*\n)+", re.MULTILINE)
new_text, n = pattern.subn(lambda m: m.group(1) + block, real_text)
if n != 1:
    raise SystemExit(f"expected exactly 1 decoding[{key}] block in {real_p}, found {n}")
real_p.write_text(new_text, encoding="utf-8")

after = yaml.safe_load(new_text)
assert after["decoding"][key] == chosen, "merge did not take"
for other in set(real["decoding"]) - {key}:
    assert after["decoding"][other] == real["decoding"][other], f"decoding[{other}] changed!"
assert after.get("diversity_penalty") == real.get("diversity_penalty"), "flat mirror changed!"
print(f"locked decoding[{key}] = {chosen}; all other entries byte-unchanged.")
PY

rm -f "$SCRATCH_SLI"
echo "Finished at $(date)"
