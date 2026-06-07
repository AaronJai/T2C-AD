# Decisions Log

A lightweight record of choices made **during implementation that deviate from the
spec** — a library behaving differently than described, an interface needing an extra
parameter, a contract that had to change. Not for pre-planned design decisions (those
live in `project-overview.md` §10) and not for routine status (that's `progress-tracker.md`).

When you pick up this project weeks later and ask "why is this the way it is?", the answer
should be here.

## How to add an entry

One row per deviation. Keep the *why* concrete.

| Date | Step | Spec said | What we did | Why |
|------|------|-----------|-------------|-----|
| 2026-06-07 | 1.1 | Prefer CyVer's internal parser for isolating the MATCH clause | Wrote a self-contained depth-aware MATCH-clause parser; did not use CyVer | CyVer's `SyntaxValidator` requires a *live* `neo4j.Driver` (it runs EXPLAIN against the DB) and exposes no offline AST/parser. Neo4j isn't available until phase 3.2, and 1.1's acceptance criteria must run now with no DB. The spec explicitly allows a targeted MATCH-clause parser. The final CyVer SyntaxValidator filtering pass still happens later in 1.2/1.3 where a driver exists. |
| 2026-06-07 | 1.1 | Implementation block declares only `extract_schema_pattern` | Also exposed `has_relationship_type(pattern) -> bool` from the same module | Acceptance criterion #2 requires testing the relationship-type *filter predicate* now. Defining it alongside extraction keeps one source of truth for "pattern has a rel type"; 1.2/1.3 import it as one clause of their exclusion filter rather than re-deriving it. |
| 2026-06-07 | 1.2 | `_syntax_ok(pattern)` runs CyVer's `SyntaxValidator` on the pattern | Made the CyVer pass *conditional*: a lazily-built validator (Neo4j driver from `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`) runs when configured; otherwise `_syntax_ok` returns True (filtering deferred) | CyVer's `SyntaxValidator` issues `EXPLAIN` against a *live* `neo4j.Driver`; Neo4j isn't available until phase 3.2, and the spec's public signatures (`build_sl_training_instance`, `build_sl_dataset`) take no driver, so there is no injection path. The now-set acceptance (criteria 1–3) exercises only node-only/parse-fail exclusions, not syntax. The full-run CyVer pass activates automatically once a DB is configured. Consistent with the 1.1 deferral above. |
| 2026-06-07 | 1.3 | The 1.1 tracker handoff predicted 1.3 would exclude rows where `has_relationship_type` is False **or** the CyVer `SyntaxValidator` fails (the same filter as 1.2) | QG excludes a row on **parse failure only** — node-only rows are kept and no rel-type or CyVer filter is applied | The 1.3 *spec* is explicit and overrides the 1.1 forward-looking note: a node-only question is still a valid QG target (the QG must learn to generate single-node Cypher), so unlike the SL adapter, QG must not drop those rows. `build_qg_training_instance` therefore returns None iff `extract_schema_pattern` is None. Not a deviation from the 1.3 spec — recorded here to reconcile it with the 1.1 handoff so a future session doesn't "fix" QG to match SL. |
| 2026-06-07 | 2.1 | "As the first sub-task… compute the token-length distribution over the 1.2 train split and set `max_seq_length` to ~the 99th percentile. Record the measured percentile and the chosen value." | Kept the spec default **`max_seq_length: 1024`** (explicitly **not** 512) and shipped `pipeline.sft.measure_token_lengths(jsonl, tokenizer)` to run the measurement; the actual percentile run is **deferred** | The 1.2 jsonl (`data/ozsoy_schema_linker_*.jsonl`) is not materialised yet — 1.2's full dataset run was itself deferred (needs the ~36k-row Ozsoy download), so there is no train split to measure against now. The measurement is offline (tokenizer only, no GPU); when the jsonl exists, run `measure_token_lengths` and, per the spec, raise toward 1536/1600 if p99 > 1024 (or lower if comfortably under) and update this row + the YAML. |
| 2026-06-07 | 2.1 | `pipeline/sft.py` declares exactly `build_model_inputs` + `run_sft` | Also exposed `measure_token_lengths(jsonl, tokenizer, percentiles)` (and a private `_percentile`) from the same module; `experiments/train_schema_linker.py` factors the spec's inline `main()` assembly into a testable `build_run_config(model_key, registry, hp)` | `measure_token_lengths` operationalises the required `max_seq_length` sub-task above (one source of truth for "how rows are tokenised", reusing `build_model_inputs`' tokenisation convention). `build_run_config` makes acceptance criterion 3 (config assembly + unknown-key exit) unit-testable without invoking `run_sft` (which would load a 7B base); `main()` calls it and is otherwise verbatim to the spec. No declared signature changed. |
| 2026-06-07 | 2.1 | (deps unspecified) | Added `pyyaml`, `accelerate`, `bitsandbytes` to `pyproject.toml` | `pyyaml` reads the two new config files (needed at import for the entry point + tests); `accelerate` backs `transformers.Trainer` and `bitsandbytes` provides the 4-bit QLoRA path — both lazily imported inside `run_sft`, so the offline test suite still runs without them. |

---

### Example of a good entry (delete once real entries exist)

| Date | Step | Spec said | What we did | Why |
|------|------|-----------|-------------|-----|
| 2026-01-15 | 3.7 | `cyver_validator` returns `properties_score: float` | Allowed `None` when the query accesses no properties | CyVer's `PropertiesValidator.validate()` returns `None` (not a score) for property-free queries; forcing a float would misreport. Type already `Optional[float]` in 0.1, so no downstream change. |

_No real entries yet._
