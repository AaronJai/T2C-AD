#!/bin/bash --login
# kaya/50_neo4j_pull.sh — run ONCE, INTERACTIVELY on the Kaya LOGIN node (NOT via sbatch).
#
# Compute nodes are offline, so the Neo4j container image must be cached as a .sif on
# /group before any sbatch job (55_neo4j.slurm) can use it. This mirrors predownload.py's
# role for the HF model/dataset cache.
set -euo pipefail

GROUP=/group/pmc084/$USER
mkdir -p "$GROUP/containers" "$GROUP/neo4j_data"/{data,logs,import,plugins}

apptainer pull "$GROUP/containers/neo4j.sif" docker://neo4j:5

echo "Cached: $GROUP/containers/neo4j.sif"
echo "Persistent DB volume: $GROUP/neo4j_data/"
echo "Next: sbatch kaya/55_neo4j.slurm"
