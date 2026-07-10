#!/bin/bash --login
#SBATCH --job-name=t2c_pole_sft_data
#SBATCH --partition=work
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.4 — generate the in-domain POLE v3 SFT data (CPU + Anthropic/OpenAI API key, no GPU).
# Writes data/pole_{sl,qg}_{train,eval}.jsonl + data/pole_{sl,qg}_train_mixed.jsonl (the Ozsoy
# replay mix the v3 continue-SFT YAMLs train on) + results/pole_sft_generation_report.json.
# Requires ANTHROPIC_API_KEY (or the backend config/pole_sft_data.yaml's paraphrase_llm names)
# exported in the submitting shell's environment. Submit from repo root:
#   sbatch kaya/73_build_pole_sft_data.slurm

set -euo pipefail

module load Anaconda3/2024.06
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

python -m experiments.build_pole_sft_data --config config/pole_sft_data.yaml
echo "Finished at $(date)"
