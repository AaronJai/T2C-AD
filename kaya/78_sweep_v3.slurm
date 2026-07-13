#!/bin/bash --login
#SBATCH --job-name=t2c_sweep_v3
#SBATCH --partition=gpu
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.5 — Gate G2 (part 1): 2.2 diversity-penalty sweep on the v3 substrate.
# Re-scans diversity_penalty ∈ {0.2,0.5,1.0} over all 120 v3 questions with sl_adapter_v3
# (the --dataset_version v3 flag → v3 schema block + `_v3` adapter suffix, pre-work 2026-07-12),
# and RE-LOCKS decoding[mistral7b] in config/schema_linker_inference.yaml. The Cov@5 ≥ 0.85
# guardrail may now be meetable (7.4 lifted sample Cov@5 to 0.800). Writes
# results/diversity_penalty_sweep_mistral7b_v3.json. Run the probe (79) AFTER this.
# Submit from repo root: sbatch kaya/78_sweep_v3.slurm

set -euo pipefail

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

python -m experiments.diversity_penalty_sweep \
    --model_key mistral7b \
    --benchmark data/benchmark-v3.json \
    --dataset_version v3 \
    --results_tag v3
echo "Finished at $(date)"
