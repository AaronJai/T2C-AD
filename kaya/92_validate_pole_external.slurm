#!/bin/bash --login
#SBATCH --job-name=t2c_validate_pole_external
#SBATCH --partition=work
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.1 — run the 9.2 benchmark validation harness against the live external-POLE graph
# served on Kaya, re-proving the Kaya-served graph is the same substrate 9.2 validated
# locally. The harness (experiments/validate_benchmark.py) is CPU-only, so this self-contained
# job starts the external-POLE Neo4j in the BACKGROUND (same node -> bolt://localhost:7687),
# loading from $MYGROUP/dumps/pole-external/neo4j.dump into the separate
# $MYGROUP/neo4j_data_pole_external dir, runs all 8 gates over data/benchmark-pole-external.json
# with --profile pole_external, and writes the report artefact. It reloads from the dump by
# default; KEEP=1 reuses the volume the 90 runner already built.
#
# The v2 graph ($MYGROUP/neo4j_data) and v3 graph ($MYGROUP/neo4j_data_v3) are never touched.
#
# Prerequisites (one time, on the LOGIN node): see kaya/90_neo4j_pole_external.slurm header
#   (kaya/50_neo4j_pull.sh for the .sif + the pole-50.dump staged as neo4j.dump).
# Submit from repo root:  sbatch kaya/92_validate_pole_external.slurm
#                    or:  KEEP=1 sbatch kaya/92_validate_pole_external.slurm  (reuse 90's volume)
# Exit code: 0 = all 8 gates green; non-zero = a gate failed (see the report + stdout).

set -euo pipefail

module load Anaconda3/2024.06
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_pole_external"
DUMP_DIR="$GROUP/dumps/pole-external"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi
if [[ ! -f "$DUMP_DIR/neo4j.dump" ]]; then
    echo "Missing $DUMP_DIR/neo4j.dump — stage the upstream pole-50.dump there first" >&2
    echo "(see kaya/90_neo4j_pole_external.slurm header for the curl command)." >&2
    exit 1
fi

# Wipe-by-default so the harness always validates against a freshly-loaded dump; KEEP=1
# reuses the volume the 90 runner built.
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

# On a fresh volume, set the password AND load the dump into the `neo4j` database BEFORE
# starting the server (offline store load; requires the DB stopped), same as the 90 runner.
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

echo "── Graph spot-check ──"
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n) AS nodes;" || true
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH ()-[r]->() RETURN count(r) AS relationships;" || true

echo "── Running validation harness (--profile pole_external) ──"
set +e
python -m experiments.validate_benchmark \
    --benchmark data/benchmark-pole-external.json \
    --profile pole_external \
    --report results/benchmark_pole_external_validation.json
RC=$?
set -e
echo "Harness exit code: $RC (0 = all 8 gates green)"
echo "Finished at $(date)"
exit $RC
