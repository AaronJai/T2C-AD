#!/bin/bash --login
#SBATCH --job-name=t2c_neo4j_pole_external
#SBATCH --partition=work
#SBATCH --time=04:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.1 — external POLE graph runner. Stands the REAL neo4j-graph-examples/pole graph
# up in Neo4j (Apptainer) for the duration of this job, in a SEPARATE data dir
# ($MYGROUP/neo4j_data_pole_external) so the v2 graph ($MYGROUP/neo4j_data) and the v3 graph
# ($MYGROUP/neo4j_data_v3) both stay intact. Same Apptainer flags as 70_neo4j_v3.slurm.
# Bolt is reachable at bolt://localhost:7687 from THIS NODE only.
#
# LOAD MECHANISM (differs from 55/70): the upstream dataset ships as a Neo4j DUMP, not a
# .cypher seed, so on a fresh volume this WIPES + loads via `neo4j-admin database load` from
# $MYGROUP/dumps/pole-external/neo4j.dump BEFORE starting the server (the offline store-file
# load requires the DB stopped), instead of the post-start cypher-shell stream 70 uses.
# Opt out with KEEP=1 to reuse the existing volume (skips wipe + load).
#
# Prerequisites (one time, on the LOGIN node — has internet):
#   1. kaya/50_neo4j_pull.sh                       # caches $MYGROUP/containers/neo4j.sif
#   2. download the upstream Neo4j-5.x dump and stage it as the load source:
#        mkdir -p $MYGROUP/dumps/pole-external
#        curl -sSL -o $MYGROUP/dumps/pole-external/neo4j.dump \
#          https://raw.githubusercontent.com/neo4j-graph-examples/pole/main/data/pole-50.dump
#      (pole-50.dump = Neo4j 5.x DZV1/zstd dump, matches the neo4j:5 image — no store upgrade
#       needed. `neo4j-admin database load neo4j` expects the file named neo4j.dump.)
#
# Usage:
#   sbatch kaya/90_neo4j_pole_external.slurm         # wipe + load from the dump
#   KEEP=1 sbatch kaya/90_neo4j_pole_external.slurm  # reuse existing volume, no reload
#   squeue -u $USER                                  # find the node it landed on
#
# Stop early with: scancel <jobid>  (neo4j is sent SIGTERM by the EXIT trap)

set -euo pipefail

GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_pole_external"
DUMP_DIR="$GROUP/dumps/pole-external"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi
if [[ ! -f "$DUMP_DIR/neo4j.dump" ]]; then
    echo "Missing $DUMP_DIR/neo4j.dump — stage the upstream pole-50.dump there first" >&2
    echo "(see the header of this script for the curl command)." >&2
    exit 1
fi

export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

# Wipe-by-default so a re-run always serves the current dump; KEEP=1 reuses the volume.
if [[ "${KEEP:-0}" -eq 1 && -d "$DATA/data/databases" ]]; then
    FRESH=0
    echo "KEEP=1 — reusing existing external-POLE volume at $DATA (no reload)."
else
    echo "Wiping external-POLE volume $DATA and loading from $DUMP_DIR/neo4j.dump."
    rm -rf "$DATA"
    FRESH=1
fi
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins"

APPT_OPTS=(--no-mount /opt --writable-tmpfs
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins"
    --bind "$DUMP_DIR:/dumps")

# On a fresh volume, set the initial password AND load the dump into the `neo4j` database
# BEFORE starting the server — both operate on the offline, bind-mounted /data store, which
# avoids the flaky change-required handshake and satisfies neo4j-admin's stopped-DB
# requirement. The dump ships as an offline store; `neo4j console` then serves it directly.
if [[ "$FRESH" -eq 1 ]]; then
    echo "Fresh volume — setting initial password via neo4j-admin"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" \
        neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"
    echo "Loading dump $DUMP_DIR/neo4j.dump into database 'neo4j'"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" \
        neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination
    echo "Dump loaded into offline store."
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

# Spot-check the load proves the SAME real graph (acceptance criterion 2):
#   nodes == 61521 (the count 9.3 confirmed live); relationships ~105.8k (9.1).
echo "── Graph spot-check ──"
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n) AS nodes;" || true
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH ()-[r]->() RETURN count(r) AS relationships;" || true

echo "Neo4j external-POLE ready: bolt://localhost:7687 (user neo4j, password \$NEO4J_PASSWORD=${NEO4J_PASSWORD})"
echo "Node: $SLURM_NODELIST — connect from a job/session on the same node."

wait "$NEO4J_PID"
