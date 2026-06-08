# Running the deferred Phase-2 GPU work on Kaya

This directory holds everything needed to run the **deferred Phase-2 acceptance work** (the
GPU jobs that couldn't run locally on the RTX 5080) on UWA's **Kaya** HPC cluster. It targets
**one base model — `mistral7b`** — on the **V100 GPU partition** in **fp16 QLoRA**.

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

`setup_env.sh` deliberately skips `CyVer`/`neo4j` (only used for dataset syntax-filtering,
which stays deferred until Neo4j exists at 3.2). `predownload.py` is the **only** step that
needs internet — every job below runs with `*_OFFLINE=1`.

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
