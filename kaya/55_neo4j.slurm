#!/bin/bash --login
#SBATCH --job-name=t2c_neo4j
#SBATCH --partition=work
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Runs SyntheticPoliceKG in Neo4j (Apptainer) for the duration of this job, for Phase-3
# steps that need a live DB (3.2 Entity Lookup onward). Apptainer shares the host network
# namespace, so bolt is reachable at bolt://localhost:7687 from THIS NODE only — for
# combined GPU+Neo4j integration runs (5.x), start this in the same job as the GPU work
# (same node) rather than as a separate job.
#
# First run: initialises the DB, sets the password, and loads data/SyntheticPoliceKG.cypher
# (takes ~30s). Subsequent runs reuse the persistent volume in $MYGROUP/neo4j_data and skip
# both.
#
# Prerequisite (one time, on the LOGIN node): kaya/50_neo4j_pull.sh
#
# Usage:
#   sbatch kaya/55_neo4j.slurm
#   squeue -u $USER                       # find the node it landed on
#   ssh <node>                            # or run your pipeline job on the same node
#   cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD"
#
# Stop early with: scancel <jobid>  (neo4j is sent SIGTERM by the EXIT trap)

set -euo pipefail

GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi

# Change this (or export NEO4J_PASSWORD before submitting) — must be >=8 chars.
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

FIRST_RUN=0
if [[ ! -d "$DATA/data/databases" ]]; then
    FIRST_RUN=1
fi

# Kaya's site-wide apptainer.conf hard-binds the HOST's /opt over the container's /opt
# (mellanox/slurm/xcat dirs), which shadows this image's JDK at /opt/java/openjdk —
# `neo4j`/cypher-shell then fail with "JAVA_HOME is not defined correctly".
# --no-mount /opt restores the image's own /opt.
#
# --writable-tmpfs gives the read-only squashfs an ephemeral overlay — neo4j needs to
# write /var/lib/neo4j/run/neo4j.pid (read-only otherwise); /data, /logs etc. are the
# bind-mounted, persistent dirs and are unaffected.
#
# `apptainer instance start` is NOT used: this image's startscript is empty (OCI
# ENTRYPOINT/CMD live in the runscript, which `instance start` does not execute), so
# the instance would come up with no neo4j process at all.
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

cshell() {
    apptainer exec --no-mount /opt "$SIF" cypher-shell -a bolt://localhost:7687 "$@"
}

# Wait for bolt to come up (default creds neo4j/neo4j, password change required).
for i in $(seq 1 60); do
    if cshell -u neo4j -p neo4j -d system "RETURN 1" >/dev/null 2>&1; then
        break
    fi
    if cshell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

if [[ "$FIRST_RUN" -eq 1 ]]; then
    echo "First run — setting password and loading data/SyntheticPoliceKG.cypher"
    cshell -u neo4j -p neo4j -d system \
        "ALTER CURRENT USER SET PASSWORD FROM 'neo4j' TO '${NEO4J_PASSWORD}'"
    cshell -u neo4j -p "$NEO4J_PASSWORD" --file data/SyntheticPoliceKG.cypher
    echo "Schema loaded."
else
    echo "Reusing existing DB volume at $DATA/data — skipping init/schema load."
fi

echo "Neo4j ready: bolt://localhost:7687 (user neo4j, password \$NEO4J_PASSWORD=${NEO4J_PASSWORD})"
echo "Node: $SLURM_NODELIST — connect from a job/session on the same node."

wait "$NEO4J_PID"
