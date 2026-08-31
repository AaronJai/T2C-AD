#!/bin/bash --login
#SBATCH --job-name=t2c_run_eval_pole_external_qwen72
#SBATCH --partition=rrifcs
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --gres=gpu:h100:4
#SBATCH --mem=400G
#SBATCH --output=logs/%x_%j.out
#SBATCH --error=logs/%x_%j.err
#
# Step 11.4 — Gate G4: the full end-to-end evaluation of the FINE-TUNED Qwen2.5-72B against the
# EXTERNAL POLE benchmark (9.2/10.1), all 100 questions x 3 conditions. run_evaluation reads
# config/pipeline_pole_external_qwen72.yaml (dataset_version: pole_external -> external
# schema/registry/prompts + the `_pole_external` adapters; results_tag: pole_external_qwen72 ->
# results/{tables,metrics,qual_records}_qwen2.5-72b_pole_external_qwen72.*), then
# analyze_qualitative.py builds the qualitative report. The external substrate is where 10.7's
# strongest single cell sits (temporal C3: EX 7/20 -> 20/20) — this run asks whether it holds at
# 2.2x the parameters.
#
# GPUs / walltime / sequencing: see the twin header in kaya/116. **gpu:h100:4**, because
# _device_maps()'s pre-11.4 2-card pinning would put QG **and** AD on one card at the
# 11.2-measured 42.5 GiB per 4-bit 72B load (~85 GiB of weights before any KV cache, with C3
# decoding beam_k=5 group beams). 3 + 3 cards exceeds k172's four, so this and kaya/116 run
# SEQUENTIALLY, unlike 10.7's side-by-side pair:
#   JID=$(sbatch --parsable kaya/116_run_evaluation_v3_qwen72.slurm)
#   sbatch --dependency=afterok:$JID kaya/117_run_evaluation_pole_external_qwen72.slurm
#
# NEO4J: the 10.1 external graph runs in the BACKGROUND inside this same job, on its OWN data dir
# (loaded from the staged dump — never the shared neo4j_data_pole_external, and never 10.7's
# _qwen_g4 volume) and its OWN per-job Bolt port, injected into a runtime copy of the config so
# the committed YAML is never mutated. The 11.4 spec is explicit that this stays even when the
# two G4s run alone — do not drop it.
#
# **GPU COUNT: 4, NOT THE SPEC'S 3 — MEASURED, NOT ASSUMED (deviation, decisions-log 2026-08-30).**
# The 11.4 spec sized this from C3's three loads alone. But run_evaluation.main() binds c1/c2/c3
# in ONE scope and HuggingFaceLLM has no teardown, so when build_condition3 runs there are SIX
# 4-bit loads resident, not three: C1's QG + C2's SL/QG + C3's SL/QG/AD = 6 x 41.5 = 249 GiB.
# (Harmless at the 32B's 20.2 GiB — 10.7 ran 121 GiB on 2 cards — and invisible until 72B.)
# A scratchpad probe replicating that exact load sequence measured both options:
#   gpu:h100:3 -> OOM. `device_map="auto"` BALANCES C1/C2 across every visible card, so by the
#     5th load the cards hold 76.2 / 78.9 / 52.6 GiB and C3's AD (pinned cuda:2) dies with
#     428 MiB free (job 1148895).
#   gpu:h100:4 -> FITS. Peak 66.5 / 69.2 / 69.1 GiB on the pinned cards, 44.3 GiB on card 3,
#     all of 93.09 — ~24 GiB of headroom on the busiest card against the 2.68 GiB k=5 decode
#     overhead 11.2 measured (job 1148924, "ALL SIX LOADS RESIDENT — no OOM").
# _device_maps() needs no further change: at device_count 4 it still returns (0, 1, 2), and
# card 3 is exactly the spill space auto uses for C1/C2. Taking all four cards does not change
# the spec's sequencing conclusion — the two G4 runs still go one after the other.
#
# Submit from repo root:  sbatch kaya/117_run_evaluation_pole_external_qwen72.slurm
#   RELOAD=1 sbatch ...   forces a re-load of the dump into this runner's volume.

set -euo pipefail

CONFIG=config/pipeline_pole_external_qwen72.yaml
RUNTIME_CONFIG=config/.pipeline_pole_external_qwen72.runtime.yaml
TAG=qwen2.5-72b_pole_external_qwen72

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

# ── external-POLE Neo4j in the background, isolated data dir AND isolated Bolt port ───────
GROUP=/group/pmc084/$USER
SIF="$GROUP/containers/neo4j.sif"
DATA="$GROUP/neo4j_data_pole_external${NEO4J_DATA_SUFFIX:-_qwen72_g4}"
DUMP_DIR="$GROUP/dumps/pole-external"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-pole-dev-password}"

BOLT_PORT="${BOLT_PORT:-$(( 20000 + SLURM_JOBID % 20000 ))}"
NEO4J_URI="bolt://localhost:${BOLT_PORT}"

if [[ ! -f "$SIF" ]]; then
    echo "Missing $SIF — run kaya/50_neo4j_pull.sh on the login node first." >&2
    exit 1
fi
if [[ ! -f "$DUMP_DIR/neo4j.dump" ]]; then
    echo "Missing $DUMP_DIR/neo4j.dump — stage the upstream pole-50.dump (see kaya/90 header)." >&2
    exit 1
fi

# Reuse this runner's own volume if it already holds the loaded store; RELOAD=1 forces a reload.
if [[ "${RELOAD:-0}" -eq 1 || ! -d "$DATA/data/databases" ]]; then
    echo "Wiping $DATA and loading from $DUMP_DIR/neo4j.dump."
    rm -rf "$DATA"; FRESH=1
else
    echo "Reusing existing external-POLE volume at $DATA."; FRESH=0
fi
mkdir -p "$DATA/data" "$DATA/logs" "$DATA/import" "$DATA/plugins" "$DATA/conf"

# Per-job Bolt port via a copied conf dir (kaya/93 pattern; see kaya/116 for the http-key note).
apptainer exec --no-mount /opt "$SIF" tar -cf - -C /var/lib/neo4j/conf . | tar -xf - -C "$DATA/conf"
sed -i 's/^server\.http\.enabled=true/server.http.enabled=false/' "$DATA/conf/neo4j.conf"
printf '\n# --- per-job overrides (kaya/117) ---\nserver.bolt.listen_address=:%s\n' \
    "$BOLT_PORT" >> "$DATA/conf/neo4j.conf"

APPT_OPTS=(--no-mount /opt --writable-tmpfs --env NEO4J_CONF=/conf
    --bind "$DATA/data:/data" --bind "$DATA/logs:/logs"
    --bind "$DATA/import:/import" --bind "$DATA/plugins:/plugins"
    --bind "$DATA/conf:/conf" --bind "$DUMP_DIR:/dumps")

if [[ "$FRESH" -eq 1 ]]; then
    echo "Fresh volume — setting initial password + loading the dump (offline store) BEFORE console"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"
    apptainer exec "${APPT_OPTS[@]}" "$SIF" \
        neo4j-admin database load neo4j --from-path=/dumps --overwrite-destination
fi

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

echo "── Graph spot-check (expect nodes 61521, relationships ~105840) ──"
cshell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(n) AS nodes;" || true

# ── Full C1+C2+C3 evaluation (100 questions x 3 conditions) ───────────────────────────────
python - "$CONFIG" "$RUNTIME_CONFIG" "$NEO4J_URI" <<'PY'
import pathlib, sys, yaml
src, dst, uri = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = yaml.safe_load(pathlib.Path(src).read_text())
cfg["neo4j"]["uri"] = uri
# RUNTIME ASSERT — layer 2 of 11.4's three properties layers, and it runs BEFORE any model is
# loaded so a failure costs seconds, not GPU-hours. Fail loudly rather than silently reproducing
# the 10.4 defect (decisions-log 2026-08-22): the local "completion" QG never sees the schema's
# property names unless this key is true, and 4 of this schema's 27 properties (incl. nhs_no)
# appear ZERO times in the QG's SFT data, so the prompt is their only possible source. Layer 1 is
# the offline key-set diff against config/pipeline_pole_external_qwen.yaml; layer 3 is
# tests/test_pipeline_configs.py, which fails offline for ANY local config missing the key.
assert cfg.get("qg_include_properties") is True, f"{src}: qg_include_properties must be true"
assert cfg["active_model"] == "qwen2.5-72b", f"{src}: unexpected active_model"
pathlib.Path(dst).write_text(yaml.safe_dump(cfg, sort_keys=False))
print(f"G0 runtime assert PASSED: qg_include_properties is True, "
      f"active_model == {cfg['active_model']!r}")
print(f"runtime config -> {dst} (neo4j.uri={uri})")
PY
python -m experiments.run_evaluation "$RUNTIME_CONFIG"

echo "Wrote results/{tables,metrics,qual_records}_${TAG}.*"

# ── Qualitative analysis on the qual records (per-type buckets) ───────────────────────────
python -m experiments.analyze_qualitative "results/qual_records_${TAG}.json"

echo "Wrote results/qualitative_analysis_${TAG}.md"
echo "Finished at $(date)"
