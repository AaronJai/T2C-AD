#!/bin/bash --login
#SBATCH --job-name=t2c_g1_cov_v3_genericonly
#SBATCH --partition=gpu
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Ablation (not a numbered phase spec — decisions-log entry only): full 120-item intrinsic
# Cov@5 / EM@1 of the PRE-7.4 generic-Ozsoy-only sl_adapter (no in-domain POLE SFT) against the
# v3 schema/benchmark. Isolates "schema redesign alone" (v2 0.208 -> this number, training data
# held fixed at generic-only) from "in-domain SFT alone" (this number -> v3's recorded 0.725,
# schema held fixed at v3). Same script as 77_g1_coverage_v3.slurm, just pointed at the
# unsuffixed adapter and writing to distinct result files so the recorded v3 gate output
# (results/g1_sl_coverage_mistral7b_v3.json, results/beams_mistral7b_v3.jsonl) is untouched.
# Submit from repo root: sbatch kaya/87_g1_coverage_v3_genericonly.slurm

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

python kaya/g1_sl_coverage_v3.py --model_key mistral7b --adapter_suffix "" \
    --results results/g1_sl_coverage_mistral7b_v3_genericonly.json \
    --beam_cache results/beams_mistral7b_v3_genericonly.jsonl
echo "Finished at $(date)"
