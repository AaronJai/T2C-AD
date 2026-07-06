#!/bin/bash --login
#SBATCH --job-name=t2c_validate_benchmark_v3
#SBATCH --partition=work
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 7.2 — run the executable benchmark validation harness against the live v3 graph.
# The harness (experiments/validate_benchmark.py) is CPU-only, so this self-contained job
# starts the v3 Neo4j in the BACKGROUND (same node → bolt://localhost:7687), loads the
# CURRENT data/SyntheticPoliceKG-v3.cypher into the separate $MYGROUP/neo4j_data_v3 dir,
# runs all 8 gates over data/benchmark-v3.json, and writes the report artefact. It reloads
# by default (seeds change between iterate-until-green runs); KEEP=1 reuses the volume.
#
# The v2 graph ($MYGROUP/neo4j_data) is never touched.
#
# Prerequisite (one time, on the LOGIN node): kaya/50_neo4j_pull.sh
# Submit from repo root:  sbatch kaya/72_validate_benchmark_v3.slurm
# Exit code: 0 = all 8 gates green; non-zero = a gate failed (see the report + stdout).

set -euo pipefail

module load Anaconda3/2024.06
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"

GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_v3"
CYPHER="data/SyntheticPoliceKG-v3.cypher"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USERNAME="neo4j"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi

# Wipe-by-default so the harness always validates against the current seed data.
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
# token under the bind-mounted /data). This avoids the flaky change-required handshake and
# lets the wait loop poll directly with the configured password.
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

echo "── Running validation harness ──"
set +e
python -m experiments.validate_benchmark \
    --benchmark data/benchmark-v3.json \
    --report results/benchmark_v3_validation.json
RC=$?
set -e
echo "Harness exit code: $RC (0 = all 8 gates green)"
echo "Finished at $(date)"
exit $RC
