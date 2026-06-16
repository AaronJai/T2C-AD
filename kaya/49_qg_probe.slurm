#!/bin/bash --login
#SBATCH --job-name=t2c_qg_probe
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
# Step 3.6 — acceptance criterion 4: run QueryGenerator.generate end-to-end over a benchmark
# sample with the trained qg_adapter, in both committed-pattern (C2/C3) and zero-shot (C1)
# modes, and confirm it emits clean MATCH…RETURN Cypher. GPU only — NO Neo4j needed (the QG
# consumes a committed pattern + schema, not entity lookups). The SL adapter is loaded only to
# source a real committed pattern, then freed before the QG adapter loads (one 7B resident at a
# time). Submit from repo root: sbatch kaya/49_qg_probe.slurm

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

python kaya/qg_probe.py --model_key mistral7b
echo "Finished at $(date)"
