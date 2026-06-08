#!/bin/bash --login
# kaya/setup_env.sh — run INTERACTIVELY on the Kaya LOGIN node (NOT via sbatch).
#
# Creates the conda env in /group (never /home — 20 GB cap) and installs deps for the
# deferred Phase-2 GPU work. PyTorch cu124 matches Kaya's cuda/12.6.3. CyVer/neo4j are
# intentionally NOT installed: they're only used for dataset syntax-filtering, which stays
# deferred until Neo4j exists at phase 3.2.
#
# Prerequisite (one time): `conda init bash && source ~/.bashrc` so `conda activate` works.
set -euo pipefail

module load Anaconda3/2024.06
module load cuda/12.6.3

GROUP=/group/pmc084/$USER
export HF_HOME=$GROUP/hf_cache
mkdir -p "$HF_HOME" "$GROUP/envs"

source "$(conda info --base)/etc/profile.d/conda.sh"

conda create -y --prefix "$GROUP/envs/t2c" python=3.11
conda activate "$GROUP/envs/t2c"

pip install --upgrade pip
# PyTorch built for CUDA 12.4 (compatible with the cuda/12.6.3 driver on Kaya).
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
# Pin transformers < 4.46 — run_sft passes TrainingArguments(evaluation_strategy=...),
# which 4.46+ renamed to eval_strategy and later removed.
pip install "transformers>=4.40,<4.46" accelerate peft bitsandbytes datasets pyyaml huggingface_hub

# Editable install of the pipeline package WITHOUT its declared deps (we installed the needed
# ones above and deliberately skip CyVer/neo4j).
pip install -e . --no-deps

echo
echo "Env ready: $GROUP/envs/t2c"
echo "Next: huggingface-cli login   (accept the Mistral-7B-v0.3 licence on HF first)"
echo "Then: HF_HOME=$HF_HOME python kaya/predownload.py"
