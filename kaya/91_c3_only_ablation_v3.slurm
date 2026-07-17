#!/bin/bash --login
#SBATCH --job-name=t2c_c3_only_ablation
#SBATCH --partition=gpu
#SBATCH --time=06:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=48G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# 8.3 follow-up (decisions-log 2026-07-16) — full 120-item C3-ONLY run testing "detected AND
# resolved" (DSR, ambiguous EA), not just binary detection, for the SL/QG training-tier ablation.
# SL and QG are swapped TOGETHER to the same tier (matching the claude-sonnet run's one-model-
# everywhere design); AD/Dis stay at the default base model, as they always have been in every
# local run (they were never fine-tuned in this project, at any tier). Needs a GPU (SL beam search
# + QG + base AD, single 4-bit load path — same class as a single condition of the recorded
# v3-mistral G4 run) and a live v3 Neo4j (Entity Lookup + CyVer + DB executor + ground-truth
# execution), so the v3 graph runs in the BACKGROUND in this same job, on an ISOLATED data
# directory (other v3 jobs may run concurrently on other nodes).
#
# Generic-Ozsoy-only (SL+QG): SL_ADAPTER_SUFFIX="" NEO4J_DATA_SUFFIX="_c3genericonly" sbatch kaya/91_c3_only_ablation_v3.slurm
# No adapters at all (SL+QG): NO_ADAPTERS=1 NEO4J_DATA_SUFFIX="_c3noadapter" sbatch kaya/91_c3_only_ablation_v3.slurm
#
# QG-properties ablation (decisions-log 2026-07-17): add QG_INCLUDE_PROPERTIES=1 to any of the
# above, plus the full-7.4-SFT tier (no SL_ADAPTER_SUFFIX/NO_ADAPTERS at all). Shows the QG the
# schema's property list — the one stage never given it on the local path. Results tag gains
# '_qgprops' so nothing collides with the recorded properties-off cells.
# Submit from repo root.

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

# ── v3 Neo4j in the background (same node), isolated data dir AND isolated Bolt port ──────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_v3${NEO4J_DATA_SUFFIX:-_c3ablation}"
CYPHER="data/SyntheticPoliceKG-v3.cypher"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

# Per-job Bolt port. NEO4J_DATA_SUFFIX isolates the data DIRECTORY but not the PORT: when Slurm
# co-locates two of these jobs on one node, both bound :7687, the loser's server failed to start,
# and its cypher-shell then silently talked to the WINNER's database — loading the v3 seed a
# second time into a live run (jobs 1063901/1063903/1063904, 2026-07-17; the survivor was
# verified uncontaminated only by counting nodes/relationships after the fact). A unique port per
# job makes that cross-talk impossible. HTTP/HTTPS are disabled outright — only Bolt is used, and
# :7474 was the second thing colliding.
BOLT_PORT="${BOLT_PORT:-$(( 20000 + SLURM_JOBID % 20000 ))}"
NEO4J_URI="bolt://localhost:${BOLT_PORT}"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi

echo "Wiping v3 volume $DATA and reloading $CYPHER (Bolt port ${BOLT_PORT})."
rm -rf "$DATA"
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins" "$DATA/conf"

# Copy the image's whole conf dir out (neo4j-admin.conf + log configs must travel with
# neo4j.conf), then append the port overrides. NEO4J_CONF points the server at it.
apptainer exec --no-mount /opt "$SIF" tar -cf - -C /var/lib/neo4j/conf . | tar -xf - -C "$DATA/conf"
# server.http.enabled is ACTIVE in the shipped conf, so it must be rewritten in place — Neo4j 5
# hard-errors ("declared multiple times") if a key is appended when it is already declared.
# server.https.enabled is already false by default; server.bolt.listen_address ships commented
# out, so it is the only one safe to append.
sed -i 's/^server\.http\.enabled=true/server.http.enabled=false/' "$DATA/conf/neo4j.conf"
printf '\n# --- per-job overrides (kaya/91) ---\nserver.bolt.listen_address=:%s\n' \
    "$BOLT_PORT" >> "$DATA/conf/neo4j.conf"

APPT_OPTS=(--no-mount /opt --writable-tmpfs --env NEO4J_CONF=/conf
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins"
    --bind "$DATA/conf:/conf")

apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"

apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j console &
NEO4J_PID=$!
cleanup() {
    echo "Stopping neo4j (pid $NEO4J_PID) at $(date)"
    kill "$NEO4J_PID" 2>/dev/null || true
    wait "$NEO4J_PID" 2>/dev/null || true
}
trap cleanup EXIT

cshell() { apptainer exec --no-mount /opt "$SIF" cypher-shell -a "$NEO4J_URI" "$@"; }

NEO4J_READY=0
for i in $(seq 1 90); do
    if cshell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1" >/dev/null 2>&1; then
        echo "Neo4j ready after ${i} checks on ${NEO4J_URI}."; NEO4J_READY=1; break
    fi
    sleep 2
done
# Fail loudly rather than falling through to a confusing load error (the old loop just gave up
# silently, which is part of why the co-location bug read as a Cypher problem).
if [[ "$NEO4J_READY" -ne 1 ]]; then
    echo "Neo4j never became ready on ${NEO4J_URI} after 180s — aborting." >&2
    exit 1
fi

echo "Loading $CYPHER"
cshell -u neo4j -p "$NEO4J_PASSWORD" --file "$CYPHER"
echo "v3 graph loaded."

# ── C3-only ablation ───────────────────────────────────────────────────────────────
# Array (not a plain string) so an explicitly-empty SL_ADAPTER_SUFFIX="" survives word
# splitting — "${VAR-default}" (no colon) only falls back when VAR is truly unset, unlike
# "${VAR:-default}" which also treats an empty string as unset.
if [[ "${NO_ADAPTERS:-0}" -eq 1 ]]; then
    SL_ARGS=(--no_adapters)
else
    SL_ARGS=(--adapter_suffix "${SL_ADAPTER_SUFFIX-_v3}")
fi
# QG properties ablation (decisions-log 2026-07-17) — tags results '_qgprops'.
if [[ "${QG_INCLUDE_PROPERTIES:-0}" -eq 1 ]]; then
    SL_ARGS+=(--qg_include_properties)
fi
python kaya/c3_only_ablation_v3.py --model_key mistral7b --neo4j_uri "$NEO4J_URI" "${SL_ARGS[@]}"
echo "Finished at $(date)"
