# Running the deferred Phase-2 GPU work on Kaya

This directory holds everything needed to run the **deferred Phase-2 acceptance work** (the
GPU jobs that couldn't run locally on the RTX 5080) on UWA's **Kaya** HPC cluster. It targets
**one base model — `mistral7b`** — on the **V100 GPU partition** in **fp16 QLoRA**.

> **From Phase 11 on the default GPU target is the `rrifcs` H100 partition, not `gpu`.**
> Jump to § [H100 on `rrifcs` (Phase 11+)](#h100-on-rrifcs-phase-11) before submitting any
> Qwen-sized (32B/72B) job — those do not fit a V100 at all. The V100 instructions below
> remain correct for the 7B `mistral7b` work of Phases 2–9.

These four artifacts are what later phases consume:

| Job | Step | Produces |
|-----|------|----------|
| `10_train_sl.slurm` | 2.1 | `checkpoints/mistral7b/sl_adapter` |
| `20_train_qg.slurm` | 2.4 | `checkpoints/mistral7b/qg_adapter` |
| `30_sweep.slurm`    | 2.2 | `config/schema_linker_inference.yaml` (locked `diversity_penalty`) + `results/diversity_penalty_sweep.json` |
| `40_probe.slurm`    | 2.3 | `results/entropy_probe_pole.json` |

A small CPU prep job (`00_build_data.slurm`) first materialises the 1.2/1.3 training jsonl,
which were never produced (they need the ~36k-row HF dataset).

> **Kaya account:** user `atan`, project `pmc084`. Group storage `/group/pmc084/atan`
> (`$MYGROUP`, 1 TB). `/home` is capped at 20 GB — keep the env, HF cache and checkpoints in
> `/group`. None of this needs Neo4j (that first matters at phase 3.2).

---

## Why fp16 (config edits on this branch)

Kaya's V100 (Volta) has **no bf16**. On the `Kaya` branch:
- `config/models.yaml` → `mistral7b` `dtype: float16`
- `config/schema_linker_train.yaml` + `config/query_generator_train.yaml` → `bf16: false, fp16: true`

Logged in `context/decisions-log.md` (2026-06-08). Don't merge these precision changes back to
`main` if `main` targets a bf16-capable GPU.

---

## One-time setup (LOGIN node — has internet)

```bash
ssh atan@kaya01.hpc.uwa.edu.au

# clone the repo into group storage (adjust if you keep it elsewhere)
cd /group/pmc084/$USER
git clone <your-repo-url> T2C-AD
cd T2C-AD
git checkout Kaya

# one time, so `conda activate` works in scripts:
module load Anaconda3/2024.06 && conda init bash && source ~/.bashrc

# create the env + install deps (PyTorch cu124, transformers<4.46, peft, bitsandbytes, …)
bash kaya/setup_env.sh

# accept the Mistral-7B-v0.3 licence on its Hugging Face page, then:
conda activate /group/pmc084/$USER/envs/t2c
export HF_HOME=/group/pmc084/$USER/hf_cache
huggingface-cli login
python kaya/predownload.py        # caches dataset + base model for the offline compute nodes
```

`predownload.py` takes `--model_key <config/models.yaml key>` (default `mistral7b`), so it is
also how you cache — or re-verify — any other base:

```bash
python kaya/predownload.py --model_key qwen2.5-32b     # 10.5/10.6
python kaya/predownload.py --model_key qwen2.5-72b     # 11.2/11.3
```

Re-running for an already-cached model re-verifies the snapshot without re-downloading, so it
doubles as the completeness check ("did all 37 shards land?").

`setup_env.sh` deliberately skips `CyVer`/`neo4j` (only used for dataset syntax-filtering,
which stays deferred until Neo4j exists at 3.2). `predownload.py` is the **only** step that
needs internet — every job below runs with `*_OFFLINE=1`. (Historical exception: the
Qwen2.5-32B and -72B snapshots were fetched with ad-hoc `huggingface-cli download` calls before
`--model_key` existed. `--model_key` restores the invariant; use it from now on.)

---

## Run the jobs (submit from the repo root)

```bash
cd /group/pmc084/$USER/T2C-AD
mkdir -p logs                      # SLURM won't create the log dir

# 1. CPU prep — materialise jsonl + print token-length percentiles
sbatch kaya/00_build_data.slurm
```

Check the output: if either **p99 > 1024**, raise `max_seq_length` in the matching train YAML
before training (see decisions-log 2.1/2.4), otherwise leave it at 1024.

```bash
# 2. Train both adapters (independent — submit both; they queue/run in parallel)
sbatch kaya/10_train_sl.slurm      # 2.1  -> checkpoints/mistral7b/sl_adapter
sbatch kaya/20_train_qg.slurm      # 2.4  -> checkpoints/mistral7b/qg_adapter

# 3. After the SL adapter finishes:
sbatch kaya/30_sweep.slurm         # 2.2  -> config/schema_linker_inference.yaml

# 4. After the sweep finishes (needs the locked penalty):
sbatch kaya/40_probe.slurm         # 2.3  -> results/entropy_probe_pole.json
```

Dependency chain: **2.1 → 2.2 → 2.3**; **2.4** is independent. To auto-gate the later jobs:

```bash
SL=$(sbatch --parsable kaya/10_train_sl.slurm)
SW=$(sbatch --parsable --dependency=afterok:$SL kaya/30_sweep.slurm)
sbatch          --dependency=afterok:$SW kaya/40_probe.slurm
sbatch kaya/20_train_qg.slurm
```

### Monitor

```bash
squeue -u $USER
tail -f logs/t2c_sl_<jobid>.out                 # watch loss; first log line at step 50
sinfo -p gpu,ondemand-gpu -o "%20P %5D %14F %10G %N"
sacct -j <jobid> --format=JobID,JobName,State,Elapsed,ReqMem,MaxRSS
```

After each training job starts, confirm `CUDA: True` and a sensible loss in the first ~50
steps before trusting the full run. The `gpu` partition allows 72 h; training is budgeted at
24 h (expect ~3–8 h per adapter on a V100), sweep/probe at 4 h.

---

## Back up the results

The four artifacts are the Phase-3 inputs. They already live under `/group` (persistent), but
copy them off-cluster too (IRDS via rclone, or `scp` to your machine):

```
checkpoints/mistral7b/sl_adapter/   checkpoints/mistral7b/qg_adapter/
config/schema_linker_inference.yaml
results/diversity_penalty_sweep.json   results/entropy_probe_pole.json
data/ozsoy_*.jsonl
```

`/scratch` is purged after 21 days — don't leave anything you need there.

---

---

## Neo4j on Kaya (for Phase 3.2+)

`50_neo4j_pull.sh` + `55_neo4j.slurm` run **SyntheticPoliceKG** in Neo4j via Apptainer,
co-located with the GPU adapters — needed once Phase 3 (Entity Lookup, 3.2 onward) requires
a live DB.

```bash
# one-time, on the LOGIN node (has internet):
bash kaya/50_neo4j_pull.sh

# per session:
sbatch kaya/55_neo4j.slurm
squeue -u $USER                 # note the JOBID and node it lands on
```

Apptainer shares the host network namespace, so bolt is reachable at
`bolt://localhost:7687` **only from that same node**. `ssh <node>` from the login node is
not available on Kaya — instead, attach to the running job's allocation with
`srun --jobid=<jobid> --overlap <command>`, e.g.:

```bash
SIF=$MYGROUP/containers/neo4j.sif
srun --jobid=<jobid> --overlap apptainer exec --no-mount /opt "$SIF" \
    cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" "MATCH (n) RETURN count(*)"
```

For a step that needs both the adapter (GPU) and the DB, run both in the same job/node —
e.g. start `55_neo4j.slurm`'s `neo4j console` invocation in the background within a GPU job
script (same `--no-mount /opt --writable-tmpfs` flags), or `salloc` a GPU node and `srun
--overlap` both pieces onto it. The DB volume persists in `$MYGROUP/neo4j_data/`, so the
password-set + schema load only happen on the very first run.

Two Apptainer quirks this script works around (see inline comments for details):
Kaya's site-wide config shadows the image's `/opt` (where its JDK lives) — fixed with
`--no-mount /opt`; and this image's `instance start` startscript is empty, so `neo4j
console` is run directly via `apptainer exec` with `--writable-tmpfs` (neo4j needs to write
its pidfile under the read-only image root).

---

## H100 on `rrifcs` (Phase 11+)

**This is the default GPU target from Phase 11 on.** Everything above this section describes
the `gpu` (V100) partition, which is where Phases 2–10.6 ran. A 32B or 72B model **will not
train on a 32 GB V100 at all** — following the older instructions gets you a step-0 CUDA OOM,
so read this section before submitting anything Qwen-sized.

### Partition facts

Verified 2026-08-29 (`scontrol show partition rrifcs` / `scontrol show node k172`):

| | |
|---|---|
| Nodes | **one** — `k172` |
| GPUs | `gpu:h100:4` — H100 **NVL**, **93.6 GiB each** (95,830 MiB; torch reports 93.1 GiB usable), **sm90** |
| Driver / toolkit | 575.57.08 · the project env's `torch 2.6.0+cu124` runs on it unmodified |
| CPU / RAM | 96 CPUs (2×48, 1 thread/core) · 1,547,000 MB (~1.5 TB) |
| `MaxTime` | `3-00:00:00` (3 days). `DefaultTime=NONE`, so **always pass `--time`** |
| Access | `AllowGroups=rrifcs-users,kaya-admins` — membership is **granted manually**; ask the HPC team / your supervisor to add you (this account was added 2026-08-28) |
| Sharing | `ExclusiveUser=NO`, `OverSubscribe=NO` |

> **Exclusivity is circumstantial, not guaranteed.** `ExclusiveUser=NO` means another
> `rrifcs-users` member's job can land on `k172` beside yours at any time; you get the whole
> node only for as long as nobody else asks. In practice it has been idle, which is exactly
> why it is worth using — but **check `sinfo`/`squeue` and queue long jobs while the node is
> quiet**, and don't design a run that breaks if two of the four cards disappear.

```bash
sinfo -p rrifcs -o "%20P %5D %14F %10G %N"     # is it up, how many GPUs are free
squeue -p rrifcs                               # who else is on k172
```

Smoke-verified 2026-08-29 (job 1144854, `--gres=gpu:h100:1`): `/group` mounts, the `t2c`
conda env activates, `torch.cuda.device_count() == 1` (Slurm isolates the requested card),
`H100 NVL sm90 93.1 GiB`. 10.6 additionally confirmed the cached `Qwen/Qwen2.5-32B`
snapshot and a bitsandbytes 0.49.2 4-bit matmul work here unmodified.

### Submit idiom

```bash
#SBATCH --partition=rrifcs
#SBATCH --gres=gpu:h100:<N>
#SBATCH --time=<always set this>
```

Every Phase-10.7 and Phase-11 runner (`kaya/103`–`kaya/110`, and 11.x's) already carries these
directives. **Any `gpu`-partition script can be redirected with the same two flags on the
`sbatch` command line — no edit to the file:**

```bash
sbatch --partition=rrifcs --gres=gpu:h100:1 --time=12:00:00 --mem=64G \
       --export=ALL,STAGE=v3 kaya/101_train_qwen_sl.slurm
```

### Measured throughput — 4.9× a V100

Qwen2.5-32B, 4-bit QLoRA, gradient checkpointing on, `per_device_train_batch_size: 1`,
`max_seq_length: 3584`:

| GPU | s / micro-step | Source |
|---|---|---|
| 1× H100 NVL (`k172`) | **3.03** | jobs **1143214** / **1143215** (10.6 `qg_adapter_v3` + `qg_adapter_pole_external`) |
| 1× v100-32gb | **14.9** | 10.5 fit-test (job 1101258) |

**≈ 4.9×.** (The two 10.6 V100 jobs that were held and re-run on H100 were tracking at
13.98 s/step when cancelled — ≈ 4.6× against that in-flight rate. Both figures are the same
finding; 14.9 s is the clean fit-test number and is the one used for the Phase-11 estimates.)
The queue win is often larger than the compute win: the 32 GB V100 nodes (k017–k020) are
routinely fragmented by multi-day single-GPU jobs, and a 2-GPU request there has waited days
while `k172` started in seconds.

### Precision: keep fp16, do **not** switch to bf16

sm90 has native bf16, and switching would be the obvious "improvement". **Don't.**
`config/models.yaml` sets `dtype: float16` and the train YAMLs set `bf16: false` / `fp16: true`
because Kaya's V100s have no bf16 — and **every adapter in this project was trained under that
one recipe**. Phase 10/11's whole argument is a model-scale comparison (7B → 32B → 72B) at a
fixed recipe; flipping precision on the H100 branch alone would confound the axis under test
with a numerics change. Four of the six Qwen-32B adapters were trained on V100s and two on the
H100 under *identical* precision, which is the only reason those six are comparable.

If you ever do switch, it is a **deviation** → record it in `context/decisions-log.md` and say
so in the tracker row (workflow rule 4).

### Sizing: one GPU per training job, run jobs in parallel

One H100 NVL card holds one 4-bit training job with room to spare — the 32B peaks at ~25 GiB on
a single card (~43.5 GiB total when `device_map="auto"` shards it over two V100s), and the 72B
is ~2.2× that, still well inside 93.6 GiB.

**So: `--gres=gpu:h100:1` for training, and run several jobs side by side.** Do **not** ask for
more cards for one training job. `run_sft` uses `device_map="auto"`, which is naive pipeline
parallelism — one GPU computes while the others idle — so sharding a single job buys nothing
and wastes the node's other cards. (Do not reach for DDP/`torchrun` either without reading
11.3: `device_map="auto"` is wrong under `torchrun`.)

**End-to-end runs are the exception.** They hold several *different* models resident at once
(SL, QG, AD), so they legitimately want more than one card:
`experiments/build_condition3.py::_device_maps()` pins one stage per device, and 11.4 requests
`--gres=gpu:h100:3` for the G4 runners (SL→`cuda:0`, QG→`cuda:1`, AD→`cuda:2`) while the
single-model probes stay on `gpu:h100:1`. See 11.4's "Device planning" note.

### Neo4j co-location: per-job Bolt port + isolated data dir

`k172` is one node, so two GPU jobs that both want a graph will collide on port 7687 and on the
Neo4j data directory unless each job gets its own. **This pattern is mandatory whenever more
than one graph-using job can be on the node at once** (which, on a single-node partition, is
always):

```bash
DATA="$GROUP/neo4j_data_v3${NEO4J_DATA_SUFFIX:-_qwen_g4}"          # isolated volume per job
BOLT_PORT="${BOLT_PORT:-$(( 20000 + SLURM_JOBID % 20000 ))}"       # derived from the job id
NEO4J_URI="bolt://localhost:${BOLT_PORT}"
printf '\n# --- per-job overrides ---\nserver.bolt.listen_address=:%s\n' \
    "$BOLT_PORT" >> "$DATA/conf/neo4j.conf"
```

**`kaya/93_run_evaluation_v3_qgprops.slurm` and `kaya/109_run_evaluation_v3_qwen.slurm` are the
canonical implementations — copy from those, don't re-derive.** They also carry the readiness
wait and the wipe-and-reload of the volume. The Apptainer quirks (`--no-mount /opt`,
`--writable-tmpfs`) are unchanged from the Neo4j section above.

---

## Gotchas (already handled in the scripts, here for debugging)

- **Offline nodes** — compute nodes have no internet; jobs set `HF_HUB_OFFLINE=1`
  `TRANSFORMERS_OFFLINE=1` `HF_DATASETS_OFFLINE=1`. If you hit a download error, the model/
  dataset wasn't cached by `predownload.py` (re-run it on the login node).
- **`evaluation_strategy`** — `run_sft` uses the pre-4.46 kwarg name; `setup_env.sh` pins
  `transformers<4.46`. If you change the pin and see a TrainingArguments error, rename it to
  `eval_strategy` in `pipeline/sft.py`.
- **MKL / `LD_PRELOAD`** — jobs `unset LD_PRELOAD` per `kaya.md`.
- **OOM** — a 7B fp16 4-bit adapter fits a 16 GB V100; if you hit CUDA OOM, lower
  `per_device_train_batch_size` (raise `gradient_accumulation_steps` to keep effective batch 32).
- **Don't run on the login node** — only `setup_env.sh` and `predownload.py` run there; all
  compute goes through `sbatch`.
