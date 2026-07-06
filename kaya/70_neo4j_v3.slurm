#!/bin/bash --login
#SBATCH --job-name=t2c_neo4j_v3
#SBATCH --partition=work
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.2 — v3 graph runner. Runs data/SyntheticPoliceKG-v3.cypher in Neo4j (Apptainer)
# for the duration of this job, in a SEPARATE data dir ($MYGROUP/neo4j_data_v3) so the v2
# graph in $MYGROUP/neo4j_data stays intact. Same Apptainer flags as 55_neo4j.slurm.
# Bolt is reachable at bolt://localhost:7687 from THIS NODE only.
#
# RELOAD SEMANTICS (differs from 55): because 7.2's iterate-until-green loop changes the
# seed data between runs, this script WIPES + reloads by default so a re-run always serves
# the current data/SyntheticPoliceKG-v3.cypher (never a stale first load). Opt out with
# KEEP=1 to reuse the existing volume (skips wipe + load).
#
# Prerequisite (one time, on the LOGIN node): kaya/50_neo4j_pull.sh
#
# Usage:
#   sbatch kaya/70_neo4j_v3.slurm            # wipe + load current v3 cypher
#   KEEP=1 sbatch kaya/70_neo4j_v3.slurm     # reuse existing v3 volume, no reload
#   squeue -u $USER                          # find the node it landed on
#
# Stop early with: scancel <jobid>  (neo4j is sent SIGTERM by the EXIT trap)

set -euo pipefail

GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_v3"
CYPHER="data/SyntheticPoliceKG-v3.cypher"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi

export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

# Wipe-by-default so the iterate-until-green loop never serves stale seed data.
if [[ "${KEEP:-0}" -eq 1 && -d "$DATA/data/databases" ]]; then
    FRESH=0
    echo "KEEP=1 — reusing existing v3 volume at $DATA (no reload)."
else
    echo "Wiping v3 volume $DATA and reloading $CYPHER."
    rm -rf "$DATA"
    FRESH=1
fi
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"

APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins")

# On a fresh volume, set the initial password BEFORE starting the server (writes the auth
# token under the bind-mounted /data), avoiding the flaky change-required handshake.
if [[ "$FRESH" -eq 1 ]]; then
    echo "Fresh volume — setting initial password via neo4j-admin"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" \
        neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"
fi

apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j console &
NEO4J_PID=$!

cleanup() {
    echo "Stopping neo4j (pid $NEO4J_PID) at $(date)"
    kill "$NEO4J_PID" 2>/dev/null || true
    wait "$NEO4J_PID" 2>/dev/null || true
}
trap cleanup EXIT

cshell() {
    apptainer exec --no-mount /opt "$SIF" cypher-shell -a bolt://localhost:7687 "$@"
}

# Wait for bolt to accept the configured password (set above on fresh, pre-existing on KEEP).
for i in $(seq 1 90); do
    if cshell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        echo "Neo4j ready after ${i} checks."
        break
    fi
    sleep 2
done

if [[ "$FRESH" -eq 1 ]]; then
    echo "Loading $CYPHER"
    cshell -u neo4j -p "$NEO4J_PASSWORD" --file "$CYPHER"
    echo "v3 graph loaded."
else
    echo "Reusing existing v3 DB volume at $DATA/data — skipping init/schema load."
fi

echo "Neo4j v3 ready: bolt://localhost:7687 (user neo4j, password \$NEO4J_PASSWORD=${NEO4J_PASSWORD})"
echo "Node: $SLURM_NODELIST — connect from a job/session on the same node."

wait "$NEO4J_PID"
