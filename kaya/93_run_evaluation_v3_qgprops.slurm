#!/bin/bash --login
#SBATCH --job-name=t2c_run_eval_v3_qgprops
#SBATCH --partition=gpu
#SBATCH --time=04:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:2
#SBATCH --mem=96G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# 8.3 follow-up (decisions-log 2026-07-17) — the full C1+C2+C3 local mistral7b v3 run with the QG
# properties fix, reading config/pipeline_v3_qgprops.yaml (results_tag: v3_qgprops →
# results/{tables,metrics}_mistral7b_v3_qgprops.{md,json}; the recorded properties-off `_v3`
# artefacts are left untouched, so the pair is a clean single-factor comparison).
#
# WHY C1 is included even though it was skipped in the SL/QG adapter ablation: C1 is structurally
# invariant to swapping ADAPTERS (build_condition1 loads none), but it is NOT invariant to this —
# it still renders a schema block, and that block was missing its Properties list. The Ozsoy
# corpus C1's zero-shot format claims comparability with is itself property-rich (90.3% of
# data/ozsoy_qg_train.jsonl rows), so properties=True is what actually honours C1's rationale.
#
# Mirrors kaya/81 (its GPU/memory reasoning applies unchanged: 4-bit/fp16 → C2 ≈ 9 GB, C3 ≈ 14 GB;
# gpu:2 lets build_condition3 pin SL→cuda:0, QG+AD→cuda:1 for C3's beam_k=5 KV spikes), plus the
# per-job Bolt port from kaya/91-92 so this can run alongside other v3 jobs on a shared node.
#
# WALLTIME (4:30, not kaya/81's 24:00): a job is only backfilled if it can FINISH before the next
# maintenance reservation — a 24h request sits PENDING with "ReqNodeNotAvail, Reserved for
# maintenance" forever and is then killed, rather than running (2026-07-17). The real run is ~3:24
# (properties-off baseline job 1032398) and the properties-on cells were faster still (fewer CyVer
# rejections → fewer retries), so 4:30 carries margin while still fitting a ~5h window.
# Submit from repo root:  sbatch kaya/93_run_evaluation_v3_qgprops.slurm

set -euo pipefail

module load Anaconda3/2024.06
module load cuda/12.6.3
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate /group/pmc084/$USER/envs/t2c

export HF_HOME=/group/pmc084/$USER/hf_cache
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
unset LD_PRELOAD

cd "$SLURM_SUBMIT_DIR"
echo "Job $SLURM_JOBID on $SLURM_NODELIST at $(date)"
nvidia-smi

# ── v3 Neo4j in the background, isolated data dir AND isolated Bolt port ──────────────────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_v3${NEO4J_DATA_SUFFIX:-_qgprops}"
CYPHER="data/SyntheticPoliceKG-v3.cypher"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

# Per-job Bolt port — see kaya/91 for the full rationale (co-located jobs both bound :7687 and
# the loser silently wrote into the winner's live database, 2026-07-17).
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
printf '\n# --- per-job overrides (kaya/93) ---\nserver.bolt.listen_address=:%s\n' \
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
if [[ "$NEO4J_READY" -ne 1 ]]; then
    echo "Neo4j never became ready on ${NEO4J_URI} after 180s — aborting." >&2
    exit 1
fi

echo "Loading $CYPHER"
cshell -u neo4j -p "$NEO4J_PASSWORD" --file "$CYPHER"
echo "v3 graph loaded."

# ── Full C1+C2+C3 evaluation with qg_include_properties: true ─────────────────────────────
# run_evaluation reads the Bolt URI from the config's neo4j.uri, so the per-job port is injected
# here rather than hardcoded in the yaml.
python - "$NEO4J_URI" <<'PY'
import sys, yaml, pathlib
cfg_path = pathlib.Path("config/pipeline_v3_qgprops.yaml")
cfg = yaml.safe_load(cfg_path.read_text())
cfg["neo4j"]["uri"] = sys.argv[1]
out = pathlib.Path("config/.pipeline_v3_qgprops.runtime.yaml")
out.write_text(yaml.safe_dump(cfg, sort_keys=False))
print(f"runtime config -> {out} (neo4j.uri={sys.argv[1]})")
PY
python -m experiments.run_evaluation config/.pipeline_v3_qgprops.runtime.yaml
echo "Finished at $(date)"
