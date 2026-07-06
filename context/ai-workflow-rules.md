# AI Workflow Rules

> This file is the entry point for every implementation session. A kickoff prompt only
> needs to say: **"Implement step `<ID>`. Follow `/context/ai-workflow-rules.md`."**
> Rule 1 chains in everything else.

---

## 1. Start of every session (the reading chain — do this in order)

Before writing any code:

1. Read `/context/project-overview.md` in full — the *what* and *why*.
2. Read this file (`ai-workflow-rules.md`) in full.
3. Open `/context/progress-tracker.md`. Confirm the step you've been asked to implement is
   `not started` or `in progress`, and that **every step it `Depends on` is marked `done`**.
   If a dependency is not done, stop and report it — do not build on a missing contract.
4. Read the step's spec at `/context/feature-specs/<ID>-<slug>.md` **completely** before
   writing anything. The spec is bounded on purpose; everything you need for this step is
   in it or in its named dependencies.

---

## 2. While implementing

- **Implement only the current step.** Do not create, edit, or "improve" files outside
  the module(s) this step owns. If you find an earlier step is wrong or incomplete, stop
  and report it — do not silently fix it mid-step.
- **Never redefine shared types or contracts.** All dataclasses, `Literal`s, and shared
  signatures live in `pipeline/types.py` (step `0.1`). Import them; never re-declare them.
  If a type or contract seems unclear, the answer is in `0.1-types.md` — don't invent one.
- **Match the public signatures the spec declares verbatim.** Downstream steps were
  designed against them. Changing a signature silently breaks a later step in a future
  session.
- **Follow `/context/code-standards.md`** for Python version, typing, docstrings, imports,
  and tests. Do not introduce a hardcoded model name anywhere outside config.

---

## 3. When the spec doesn't resolve something

If you hit a genuine ambiguity the spec and its dependencies do not answer: **stop and
ask.** Do not silently pick an option. A blocked step recorded clearly is cheaper than a
wrong contract that propagates across sessions.

---

## 4. When you deviate from the spec

If you must do something different from what the spec says (a library doesn't behave as
described, an interface needs an extra parameter, etc.):

1. Make the smallest deviation that works.
2. Record it in `/context/decisions-log.md` as: **date · step · what the spec said · what
   you did · why.**
3. Note it in the step's `progress-tracker.md` row.

An undocumented deviation is the single most expensive thing for a future session to debug.

---

## 5. End of every session (completion handoff)

When the step is done:

1. Run (or describe, if it requires GPU/Neo4j and those aren't available) the step's
   **Acceptance criteria** from the spec. State which checks passed and which are deferred.
2. Update the step's row in `/context/progress-tracker.md`: set `Status`, fill in
   `Outputs` (the importable names/files produced) and a one-line `Handoff` note stating
   **what the next step can now import and rely on**.
3. End with a short summary: what was built, what it exposes, and what the next step
   expects from it.

---

## 6. Standing reminders

- Spec files are named `<ID>-<slug>.md` (e.g. `0.1-types.md`, `3.4-ambiguity-detector.md`)
  and live in `/context/feature-specs/`. There is no `spec-` prefix.
- **Dataset versions (amended 2026-07-06).** `data/benchmark-updated.json` +
  `data/SyntheticPoliceKG.cypher` are the **v2** artefacts — canonical for Phases 0–6
  and **frozen** as the recorded baseline (job 957276 results). Never edit them.
  Phase 7 builds the **v3** dataset (`data/SyntheticPoliceKG-v3.cypher`,
  `data/benchmark-v3.json`); v3 becomes canonical for all new runs once the 7.2
  validation harness passes green on live Neo4j. Both versions share the same item
  contract: `ambiguity_type ∈ {schema, entity, intent, temporal, null}`. There is no
  migration/remapping step for either — v3 is authored to the contract, not migrated;
  do not write one.
- Model backends are swappable by config. Default base model is Mistral 7B, but it is an
  example default only; nothing may assume it.
- Entity Lookup and any validation/execution/evaluation step need a **live Neo4j** with
  the KG loaded. If the database isn't available, implement against the contract and mark
  validation deferred — do not stub the data.

---

## 7. Kaya cluster ops (GPU + Neo4j availability)

As of 2026-06-15, Phase 2 is fully complete: both adapters are trained
(`checkpoints/mistral7b/{sl_adapter,qg_adapter}`), and the 2.2/2.3 GPU probes have run.
A GPU and a live Neo4j (loaded with SyntheticPoliceKG) are both available on Kaya — so
**3.1 onward generally should NOT defer GPU/Neo4j acceptance criteria**; run them for real
in the implementing session.

- **GPU steps** (3.1, 3.6, and anything loading the trained adapters): submit a short
  `kaya/*.slurm` job (follow the pattern in `kaya/30_sweep.slurm`/`kaya/40_probe.slurm` —
  `sbatch`, then check `logs/<name>_<jobid>.out/.err`). Don't try to load a 7B model on
  the login node.
- **3.2 (Entity Lookup) and any step needing live Neo4j**: `sbatch kaya/55_neo4j.slurm`,
  note the job's node from `squeue --me`, then reach `bolt://localhost:7687` via
  `srun --jobid=<id> --overlap <command>` (full details + the `cypher-shell` example in
  `kaya/README.md` § "Neo4j on Kaya (for Phase 3.2+)"). Bolt is only reachable from that
  job's node — not via plain `ssh`.
- If a step needs **both** GPU and Neo4j, either start the Neo4j console in the
  background within the GPU job script (same `--no-mount /opt --writable-tmpfs` flags as
  `55_neo4j.slurm`), or `salloc` a GPU node and `srun --overlap` both pieces onto it.
- Record any new compute-driven deviation found while running these (library bugs,
  OOMs, format mismatches) in `decisions-log.md` per rule 4 — e.g. the `transformers`
  group-beam-search `compute_transition_scores` off-by-one found 2026-06-15.

---

## 8. Python environment (read when the prompt says "we are developing in Kaya")

There is a project conda env — **use it for every `python` / `pytest` invocation**. The
login-node base anaconda has NO `torch`, so running tests against it raises
`ModuleNotFoundError: No module named 'torch'` on the GPU-touching modules (`tests/test_sft.py`,
`tests/test_probe_utils.py`, `tests/llm/`, `tests/schema_linker/`, `tests/query_generator/`).
That error means the wrong interpreter — not a broken step.

- **Env:** `/group/pmc084/atan/envs/t2c` (torch 2.6.0+cu124, transformers, pytest, rapidfuzz,
  neo4j, …). A sibling `pytorch_env` also exists; `t2c` is the project one. Env spec lives at
  `/group/pmc084/atan/envs/environment.yml`.
- **Activate before running anything Python:**
  ```bash
  source activate /group/pmc084/atan/envs/t2c
  ```
- **Run the full suite from the repo root** after activating: `python -m pytest -q` (expect a
  green suite; record the count in the step's handoff note).
- New runtime deps still get declared in `pyproject.toml` per `code-standards.md`; if a dep is
  missing from the env, install it into `t2c` (don't fall back to base) and note it.
