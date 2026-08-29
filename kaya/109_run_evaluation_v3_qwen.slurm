#!/bin/bash --login
#SBATCH --job-name=t2c_run_eval_v3_qwen
#SBATCH --partition=rrifcs
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --gres=gpu:h100:2
#SBATCH --mem=160G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 10.7 — Gate G4: the full end-to-end evaluation of the FINE-TUNED Qwen2.5-32B against the
# v3 ("custom") benchmark, all 120 questions x 3 conditions. run_evaluation reads
# config/pipeline_v3_qwen.yaml (dataset_version: v3 -> v3 schema/registry/prompts + the `_v3`
# adapters via adapter_suffix_for_version; results_tag: v3_qwen -> results/
# {tables,metrics,qual_records}_qwen2.5-32b_v3_qwen.*), then analyze_qualitative.py builds the
# qualitative report from the qual records.
#
# NOTE (spec name): the 10.7 spec named this runner kaya/100_run_evaluation_v3_qwen.slurm;
# 100-103 were already claimed by 10.4/10.6, so it is renumbered to 109 (same renumbering the
# 10.4 runner needed — decisions-log 2026-08-22 / 2026-08-28). Same contents the spec describes.
#
# GPUs: gpu:h100:2 so build_condition3's _device_maps() pins SL -> cuda:0 and QG + AD -> cuda:1
# (decisions-log 2026-06-26). Three 4-bit/fp16 32B loads at the 10.5-measured 20.2 GiB each =
# 20 GiB on card 0 and 40 GiB on card 1, comfortably inside a 93.6 GiB H100 NVL even with C3's
# beam_k=5 KV spikes. Two GPUs also leaves the other two cards on k172 free, so this and
# kaya/110 (the external G4) can run side by side.
#
# WALLTIME: 10.4's Mistral-7B external G4 took 2h55m for 100x3 on 2x V100. Qwen-32B on an H100
# measured ~7 s/item for k=5 SL beams (10.6 cov-check job 1144336) vs ~5 s/item for Mistral on a
# V100, and the QG's 256 greedy tokens are correspondingly slower, so budget ~3x: 24 h carries
# ample margin for 120x3. (rrifcs allows 3 days; there is no maintenance reservation to fit
# inside, unlike the situation kaya/93's header describes for the `gpu` partition.)
#
# NEO4J: needs BOTH a GPU and a live v3 graph, so the v3 graph runs in the BACKGROUND inside this
# same job, on its OWN data dir and its OWN per-job Bolt port (kaya/91's 2026-07-17 finding: two
# co-located jobs both bound :7687 and the loser silently wrote into the winner's live database).
# The port is injected into a runtime copy of the config, so the committed YAML is never mutated.
#
# Submit from repo root:  sbatch kaya/109_run_evaluation_v3_qwen.slurm

set -euo pipefail

CONFIG=config/pipeline_v3_qwen.yaml
RUNTIME_CONFIG=config/.pipeline_v3_qwen.runtime.yaml
TAG=qwen2.5-32b_v3_qwen

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

# ── v3 Neo4j in the background, isolated data dir AND isolated Bolt port (kaya/93 pattern) ──
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_v3${NEO4J_DATA_SUFFIX:-_qwen_g4}"
CYPHER="data/SyntheticPoliceKG-v3.cypher"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

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
# neo4j.conf), then apply the port overrides. server.http.enabled is ACTIVE in the shipped conf
# so it must be rewritten in place — Neo4j 5 hard-errors on a key declared twice; the bolt
# listen address ships commented out, so it is the only one safe to append (kaya/93).
apptainer exec --no-mount /opt "$SIF" tar -cf - -C /var/lib/neo4j/conf . | tar -xf - -C "$DATA/conf"
sed -i 's/^server\.http\.enabled=true/server.http.enabled=false/' "$DATA/conf/neo4j.conf"
printf '\n# --- per-job overrides (kaya/109) ---\nserver.bolt.listen_address=:%s\n' \
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
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n) AS nodes;" || true
echo "v3 graph loaded."

# ── Full C1+C2+C3 evaluation (120 questions x 3 conditions) ───────────────────────────────
# run_evaluation reads the Bolt URI from the config's neo4j.uri, so the per-job port is injected
# into a runtime COPY here rather than mutating the committed YAML.
python - "$CONFIG" "$RUNTIME_CONFIG" "$NEO4J_URI" <<'PY'
import pathlib, sys, yaml
src, dst, uri = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = yaml.safe_load(pathlib.Path(src).read_text())
cfg["neo4j"]["uri"] = uri
# Fail loudly rather than silently reproducing the 10.4 defect (decisions-log 2026-08-22): the
# local "completion" QG never sees the schema's property names unless this key is true.
assert cfg.get("qg_include_properties") is True, f"{src}: qg_include_properties must be true"
assert cfg["active_model"] == "qwen2.5-32b", f"{src}: unexpected active_model"
pathlib.Path(dst).write_text(yaml.safe_dump(cfg, sort_keys=False))
print(f"runtime config -> {dst} (neo4j.uri={uri}, qg_include_properties=True)")
PY
python -m experiments.run_evaluation "$RUNTIME_CONFIG"

echo "Wrote results/{tables,metrics,qual_records}_${TAG}.*"

# ── Qualitative analysis on the qual records (per-type buckets) ───────────────────────────
python -m experiments.analyze_qualitative "results/qual_records_${TAG}.json"

echo "Wrote results/qualitative_analysis_${TAG}.md"
echo "Finished at $(date)"
