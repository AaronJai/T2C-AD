# Handover — T2C Disambiguation Pipeline (UWA Honours)

_Last updated: end of the spec-writing + parameterisation session._

## What this project is

A multi-agent Text-to-Cypher pipeline whose research contribution is making **ambiguity an
explicit, named pipeline stage** — where prior systems silently commit to one interpretation
during schema linking, this one detects ambiguity, records it, and resolves it deliberately. It
runs over a synthetic police knowledge graph (POLE schema) in Neo4j and is evaluated in three
conditions: **C1** zero-shot baseline → **C2** schema-grounded (fine-tuned) → **C3**
disambiguation-enhanced. The thesis claim is that C3 (and C2) beat C1, demonstrating the value of
explicit disambiguation. The 125-question typed ambiguity benchmark is the primary deliverable;
the pipeline is the instrument.

## Current status

- **All 27 implementation specs + 5 governance files are written** and live in `/context/`.
- The repo currently contains `/context/` (governance + specs) and `data/benchmark-updated.json`.
  **No pipeline code is implemented yet** — implementation is the next phase.
- The plan is fully bounded: each step has dependencies, exact code/contracts, edge cases, and
  acceptance criteria split into "runnable now (no GPU/DB)" vs "deferred (GPU/DB)".

## Repository layout

```
/context/
  ai-workflow-rules.md      # self-bootstrapping entry point for the implementing agent
  project-overview.md       # architecture, scope, success criteria
  code-standards.md         # Python >=3.10, pytest, import rules, deps in pyproject
  decisions-log.md          # record deviations / resolved flags here as you build
  progress-tracker.md       # all 27 steps in dependency order + full module build map
  feature-specs/            # 0.1 … 6.2 — one bounded spec per step
data/
  benchmark-updated.json    # canonical 125-question benchmark (already validated, already placed)
```

Everything else (`pipeline/`, `experiments/`, `config/`, `checkpoints/`, `app/`) is created by the
implementing agent, in the order and locations given by the build map in `progress-tracker.md`.

## How to implement

**Per-step prompt (the whole thing):**

> `Implement step <ID>. Follow /context/ai-workflow-rules.md.`

That rules file makes the agent read the overview → rules → tracker (check deps are `done`) → the
full spec, implement **only that step**, log any deviation in `decisions-log.md`, and update the
tracker with status + a handoff note. Start at `0.1`, go in dependency order, **one step per
session**. Don't batch steps — the per-step handoff discipline is the point.

**Model choice for the agent:** Sonnet is sufficient for ~20 of the 27 steps (the specs front-load
the hard reasoning), run with reasoning effort up. Use **Opus for the intricate steps**: `0.1`
(foundational types), `1.1` (Cypher parsing), `3.1` (beam alignment), `3.4`/`3.5` (parsing +
fallback logic), `5.2` (the three-loop orchestrator). Use **Claude Code** as the harness.

## Before you start — setup checklist

The specs assume packaging works and deps exist but don't create that scaffolding. Set up first:

1. **Python ≥3.10 virtualenv** (3.11 recommended; match your HPC environment). 3.10 is the true
   floor — `@dataclass(kw_only=True)` in step 5.1 requires it.
2. **`pyproject.toml`** — makes `from pipeline... import` resolve in tests and tracks dependencies.
3. **`.gitignore`** — `.venv/`, `__pycache__/`, `checkpoints/`, `results/`, `*.jsonl`, HF caches.
4. **`CLAUDE.md` at repo root** — a thin pointer (~25 lines) telling Claude Code to read and follow
   `/context/ai-workflow-rules.md` before any work, plus the few always-on guardrails (implement
   only the current step; types only from `pipeline/types.py`; never hardcode a model name outside
   config; dependency order; ask if genuinely ambiguous). Do **not** duplicate the governance files
   into it.
5. **One line in `code-standards.md`**: declare new runtime deps in `pyproject.toml` when a step
   first needs them (prevents ad-hoc `pip install` drift, important for HPC reproducibility).

**Not needed until their phases:** Neo4j (first needed at 3.2), a GPU / any models / ML libraries
(2.1). Step 0.1 is pure stdlib + pytest.

## Phases at a glance

- **Phase 0 — Foundations.** Shared types, model interface (`build_llm`), POLE schema in code,
  benchmark loader. Contracts only.
- **Phase 1 — Training data.** Turn the Neo4j Text2Cypher 2025v1 dataset into SL and QG SFT data;
  defines the schema-pattern format the pipeline keys off.
- **Phase 2 — Train + sanity.** LoRA fine-tune the Schema Linker and Query Generator; lock the
  diversity-penalty (sweep); validate the entropy signal (probe).
- **Phase 3 — The pipeline.** The eight runtime components in data-flow order (Schema Linker →
  Entity Lookup → Bayesian scorer → Ambiguity Detector → Disambiguator → Query Generator → CyVer →
  DB executor). This is the actual contribution.
- **Phase 4 — Measuring.** Semantic evaluator (EX / relaxed AREA / failure mode) + the metric
  bundle and Tables 1–3.
- **Phase 5 — Integration.** Components container, orchestrator (three feedback loops), per-
  condition builders, config-driven harness. Produces the experiment.
- **Phase 6 — Optional extras.** Cosine pre-filter (scalability, off by default) and a Gradio demo
  (interactive-disambiguation stub made tangible). Not on the critical path.

The argument spine is Phase 3 → 5 → 4: build explicit disambiguation, run it in three conditions,
let the metrics show whether it earns its keep.

## Key decisions locked this session

- **Dataset → `neo4j/text2cypher-2025v1`** (~40.4K; 35.9K train / 4.44K test, Apache-2.0). Six
  fields documented in 1.2/1.3. The `schema` field is **heterogeneous** (varies by `data_source`);
  the decision is to **feed it raw** — training across formats teaches format-robustness. No manual
  download; `load_dataset(...)` auto-caches. We use the dataset's `train` split directly (no
  self-split); a separate 90:10 slice off `train` is the fine-tuning **validation** set, distinct
  from the dataset `test` split.
- **`build_qg_prompt` takes a `schema_block: str`** (not a `SchemaRepr`), mirroring `build_sl_prompt`
  — required for QG training on raw heterogeneous schema strings.
- **Intrinsic eval on the held-out test split was CUT** as a thesis deliverable (C2-over-C1 on POLE
  already proves the components work; a fourth eval axis is write-up overhead without supporting the
  disambiguation claim). Kept only as an **informal post-training Cov@5/EM@1 spot-check** reusing
  `probe_utils` — not specced, not reported.
- **`max_seq_length`:** do **not** keep the original 512 (truncates long 2025v1 schemas). First
  sub-task of 2.1 measures the token-length distribution and sets it (default 1024); 2.4 re-measures
  (QG prompts run longer).
- **Multi-base model registry.** `config/models.yaml` keys bases by `model_key` (base,
  `target_modules`, dtype, `load_in_4bit`); training YAMLs hold only shared hyperparameters; adapters
  namespace under `checkpoints/{model_key}/{sl,qg}_adapter`; the harness selects a base via
  `active_model`. **Adding a base later = one registry entry.** Training/evaluating a base = pass
  `--model_key` / set `active_model`. Mistral and Llama 3.1 share `target_modules` (`q_proj`,
  `v_proj`); a LoRA adapter is bound to its base (train one adapter per base, pair at inference).
- **5.1/5.2 reconciliation.** `PipelineComponents` holds the **constructed** stage objects
  (`SchemaLinker`, `QueryGenerator`) + the loaded entity cache + CyVer validators, not raw LLMs;
  uses `@dataclass(kw_only=True)`. The orchestrator calls the real Phase 3 APIs.
- **Bug fixes folded in:** `run_condition` returns `ad_predictions` (the pass's undefined
  `c3_states`); ground-truth queries use `.data()` to match `db_executor`'s extraction; benchmark
  loads via `load_benchmark` (0.4).

## Decisions parked for implementation time (resolve + log in `decisions-log.md`)

- **`_build_cypher_pattern` branching** (0.1) — linear skeleton specified; branching flagged as
  low-stakes since it's a QG prompt hint.
- **Neo4j transaction-timeout mechanism** (3.8) — version-dependent; set a server-side tx timeout
  and adapt to the installed driver.
- **Disambiguator typed-only constraint** (3.5) — it may emit patterns the QG didn't see verbatim
  (e.g. untyped `-[r]->`); if that degrades QG output, constrain to typed candidates.
- **Per-base `diversity_penalty`** (2.2) — if you train more than one base, key the locked penalty
  by `model_key` in `schema_linker_inference.yaml` and have 5.4 read its `active_model`'s entry.
- **`embedding_model` on builders** (5.4) — currently set on C1/C2 after build; optionally add it to
  all three builder signatures.
- **Single base vs base-model comparison** — the thesis result needs one base; comparing Mistral vs
  Llama is an optional robustness axis (extra runs + write-up). Decide with your supervisors.

## Compute & environment

- **Local RTX 5080 (16 GB):** use **QLoRA / 4-bit** (`load_in_4bit: true` — already the registry
  default) — a 7–8B base won't fit in bf16 on 16 GB. Expect **~3–6 h per adapter**, ~6–12 h for both
  — an overnight job, not weeks. Do a small smoke-train first to validate the pipeline end-to-end.
- **UWA Kaya HPC** (worth setting up for iteration/parallelism): SLURM-based; apply via IT Helpdesk;
  docs at `docs.hpc.uwa.edu.au` (UWA network / UniConnect VPN only). Two gotchas: **no persistent
  storage** (stage data in, back adapters out to iRDS), and **compute nodes often have no internet**
  (pre-download the base model + dataset on a login node, or staging will fail). Exact GPU models
  are in the access docs. Pawsey/Setonix is the tier above if ever needed.

## Cross-cutting threads to watch (span multiple specs)

- **Committed-pattern format consistency:** `extract_schema_pattern` (1.1) defines the format that
  `_build_cypher_pattern` (0.1) and the Disambiguator (3.5) must match, or the QG sees an unfamiliar
  style. 1.3 acceptance test 3 is the guard.
- **Locked `diversity_penalty` flow:** 2.2 → `config/schema_linker_inference.yaml` → 3.1 / 5.3; 5.4
  fails loudly if missing.
- **Prompt sharing prevents train/inference skew:** the SL and QG prompt builders live at the
  training step (1.2/1.3) and are imported (never duplicated) at inference (3.1/3.6/5.3).
- **Types discipline:** all shared types come from `pipeline/types.py` (0.1); never redefine them.
