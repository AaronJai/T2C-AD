#!/bin/bash --login
#SBATCH --job-name=t2c_cyver_probe
#SBATCH --partition=work
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 3.7 — acceptance criterion 6: build the three REAL CyVer validators against the live
# SyntheticPoliceKG (POLE) graph and confirm cyver_validator routes crafted queries
# (valid / bad-syntax / bad-label / bad-property) to the spec's route_to targets. CyVer needs
# only a live Neo4j (no GPU), so Neo4j runs in the BACKGROUND inside this CPU `work` job
# (same node → bolt://localhost:7687), per kaya/README.md §"Neo4j on Kaya" and
# ai-workflow-rules.md §7. Submit from repo root: sbatch kaya/57_cyver_probe.slurm
#
# Prerequisites: kaya/50_neo4j_pull.sh (one-time) and a first-run Neo4j load
# (data/SyntheticPoliceKG.cypher persists in $MYGROUP/neo4j_data after 55_neo4j.slurm).

set -euo pipefail

module load Anaconda3/2024.06
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

# ── Neo4j in the background (same node → bolt://localhost:7687) ──────────────────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi
if [[ ! -d "$DATA/data/databases" ]]; then
    echo "Neo4j volume $DATA not initialised — run kaya/55_neo4j.slurm once first to load the KG." >&2
    exit 1
fi

# Same Apptainer flags as 55_neo4j.slurm (--no-mount /opt restores the image JDK;
# --writable-tmpfs lets neo4j write its pid file on the read-only image root).
APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins")
apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j console &
NEO4J_PID=$!
cleanup() {
    echo "Stopping neo4j (pid $NEO4J_PID) at $(date)"
    kill "$NEO4J_PID" 2>/dev/null || true
    wait "$NEO4J_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for bolt to accept the configured password (DB already initialised on a prior run).
for i in $(seq 1 60); do
    if apptainer exec --no-mount /opt "$SIF" \
        cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" \
        >/dev/null 2>&1; then
        echo "Neo4j ready after ${i} checks."
        break
    fi
    sleep 2
done

python kaya/cyver_probe.py
echo "Finished at $(date)"
