# Progress Tracker

> Single source of truth for build status across sessions. Update the relevant row at the
> **start** of a step (→ `in progress`) and at the **end** (→ `done`, with Outputs +
> Handoff). Do not start a step whose dependencies aren't all `done`.

**Status legend:** `not started` · `in progress` · `done` · `blocked` (note why in the row)

---

## Phase 0 — Contracts & Foundations *(no model, no DB)*

| Step | Spec file | Depends on | Status | Outputs / Handoff note |
|------|-----------|------------|--------|------------------------|
| 0.1 | `0.1-types.md` | — | done | `pipeline/types.py` + `pipeline/__init__.py`. Exports all shared dataclasses (`SchemaElement`, `SchemaRepr`, `SchemaCandidate`, `CandidateMapping`, `EntityCandidate`, `EntityLookupResult`, `AmbiguityResult`, `SchemaMapping`, `ValidationResult`, `ExecutionResult`, `BenchmarkItem`, `EvaluationResult`, `PipelineState`), the 7 type literals, and `_build_cypher_pattern`. Handoff: every later step imports its contracts from `pipeline.types`; no type here is redefined elsewhere. All 4 contract tests pass (`tests/test_types.py`). |
| 0.2 | `0.2-llm.md` | — | done | `pipeline/llm/` package: `base.py` (`BaseLLM` ABC, `GenerationConfig`, `Completion`), `huggingface.py` (`HuggingFaceLLM`), `openai.py` (`OpenAILLM`), `anthropic.py` (`AnthropicLLM`), `__init__.py` (re-exports + `build_llm` factory). Handoff: later steps `from pipeline.llm import BaseLLM, GenerationConfig, Completion, build_llm`. SL (3.1)/QG (3.6) hold an injected `BaseLLM`; condition builders (5.3) call `build_llm(spec)` from config. No module hardcodes a model name. Now-set acceptance (clean import, abstract ABC + FakeLLM ranking, factory dispatch/ValueError) pass via `tests/llm/test_base.py` (6 tests). Integration checks (real HF beam scores, OpenAI/Anthropic smoke) deferred — need GPU/API keys. |
| 0.3 | `0.3-schema.md` | 0.1 | done | `pipeline/schema.py` exposes `build_pole_schema_repr() -> SchemaRepr` (9 node labels, 28 relationship paths, node + temporal-edge property lists; `format="nodes_and_paths"`). Built once from fixed definitions, not read from Neo4j. Handoff: prompt-building stages (3.1, 3.4, 3.6, 5.1, 6.1) import it and serialise via `SchemaRepr` methods from 0.1 — no consumer constructs a `SchemaRepr` by hand. Now-set acceptance (counts; label/rel-type consistency with `SyntheticPoliceKG.cypher`; serialiser substrings + one cypher line per path) passes via `tests/test_schema.py` (3 tests). Integration check (parity with live `db.labels()`/`db.relationshipTypes()`) deferred — needs Neo4j. |
| 0.4 | `0.4-benchmark-loader.md` | 0.1 | done | `pipeline/data/__init__.py` + `pipeline/data/benchmark_loader.py` exposing `load_benchmark(path) -> list[BenchmarkItem]`, `ambiguous_items(items)`, `items_by_type(items)`. No remapping — loads the canonical file and validates defensively (invalid/empty/compound `ambiguity_type`, `is_ambiguous`↔type mismatch, interpretation-presence mismatch all raise `ValueError`). Handoff: 5.4 (eval harness) and 2.2/2.3 (probe) import these to load the identical 125-item set; `ambiguous_items` gives the 50-question subset, `items_by_type` the stratified groups (schema=13, entity=11, intent=11, temporal=15, None=75). All acceptance criteria pass via `tests/data/test_benchmark_loader.py` (6 tests). **Phase 0 complete.** |

## Phase 1 — Training Data Prep

| Step | Spec file | Depends on | Status | Outputs / Handoff note |
|------|-----------|------------|--------|------------------------|
| 1.1 | `1.1-pattern-extraction.md` | 0.1 | done | `pipeline/schema_linker/__init__.py` + `pipeline/schema_linker/pattern_extraction.py` exposing `extract_schema_pattern(cypher) -> Optional[str]` (canonical committed-pattern format) and `has_relationship_type(pattern) -> bool` (the rel-type exclusion predicate). Self-contained depth-aware MATCH-clause parser — CyVer not used (needs live driver; see decisions-log). Handoff: 1.2 builds SL targets and 1.3 builds QG `committed_pattern` by calling `extract_schema_pattern`, then excluding rows where it returns `None`, `has_relationship_type` is False, or the CyVer SyntaxValidator (live driver) fails. Output format is the contract `_build_cypher_pattern` (0.1) and 3.5 must match. All acceptance criteria pass via `tests/schema_linker/test_pattern_extraction.py` (14 tests); CyVer SyntaxValidator filtering deferred to 1.2/1.3 (needs Neo4j). |
| 1.2 | `1.2-sl-training-data.md` | 1.1, 0.3 | done | `pipeline/schema_linker/prompts.py` (`SL_SYSTEM`, `build_sl_prompt(question, schema_block)` — the shared train/inference prompt contract) + `pipeline/schema_linker/training_data.py` (`load_ozsoy_split`, `build_sl_training_instance`, `build_sl_dataset` → writes `data/ozsoy_schema_linker_train.jsonl` + `_eval.jsonl`, returns kept/excluded-by-reason report). Per-row filter = parse-fail (`extract_schema_pattern` None) / node-only (`has_relationship_type` False) / CyVer `SyntaxValidator`. CyVer pass is conditional on a live Neo4j driver (env-configured) and deferred otherwise — see decisions-log. Handoff: 2.1 trains on the two jsonl files (`{"prompt","completion"}` lines, completion-only loss); 3.1 imports `build_sl_prompt` verbatim. Now-set acceptance (criteria 1–3) passes via `tests/schema_linker/test_training_data.py` (6 tests); full-run yield (~85–90%) + CyVer syntax filtering deferred (needs dataset + Neo4j). |
| 1.3 | `1.3-qg-training-data.md` | 1.1 | done | `pipeline/query_generator/__init__.py` + `pipeline/query_generator/prompts.py` (`SYSTEM_PROMPT_WITH_PATTERN`, `SYSTEM_PROMPT_ZERO_SHOT`, `build_qg_prompt(question, schema_block, committed_pattern=None)` — shared train/inference/C1 prompt; with-pattern → C2&C3, without → C1 zero-shot) + `pipeline/query_generator/training_data.py` (`build_qg_training_instance`, `build_qg_dataset` → writes `data/ozsoy_qg_train.jsonl` + `_eval.jsonl`, returns counts report). QG `completion` = full gold Cypher verbatim; `committed_pattern` = `extract_schema_pattern(gold)`. Per-row filter = parse-fail ONLY (node-only rows are KEPT — valid QG targets; no rel-type/CyVer filter, unlike 1.2; see decisions-log 2026-06-07). Same `seed=13` as 1.2 → consistent SL/QG partition. Handoff: 2.4 trains on the two jsonl files (`{"prompt","completion"}` lines, completion-only loss); 3.6 (inference) + 5.3 (C1 zero-shot) import `build_qg_prompt` verbatim. Now-set acceptance (criteria 1–3, incl. the train↔inference format-consistency guard) passes via `tests/query_generator/test_training_data.py` (9 tests); full-run yield (~90% of 35.9k) deferred (needs dataset). **Phase 1 complete.** |

## Phase 2 — Training & Probe Checkpoints *(GPU + Ozsoy data)*

| Step | Spec file | Depends on | Status | Outputs / Handoff note |
|------|-----------|------------|--------|------------------------|
| 2.1 | `2.1-sl-training.md` | 1.2, 0.2 | done | `pipeline/sft.py` (`build_model_inputs` — completion-only loss masking; `run_sft(config) -> adapter_path` — LoRA/QLoRA harness reused unchanged by 2.4; `measure_token_lengths` — `max_seq_length` sub-task helper) + `config/models.yaml` (base registry: `mistral7b`, `llama31-8b`; per-model `base`/`target_modules`/`dtype`/`load_in_4bit`) + `config/schema_linker_train.yaml` (shared hyperparameters only; `max_seq_length: 1024`, not 512) + `experiments/train_schema_linker.py` (`--model_key`; `build_run_config` merges registry+hp → namespaced `checkpoints/{model_key}/sl_adapter`; unknown key exits with known list). Handoff: 2.4 reuses `pipeline/sft.py` + `config/models.yaml` verbatim (QG = own YAML + `qg_adapter`); 3.1 loads `checkpoints/{model_key}/sl_adapter` via `HuggingFaceLLM(base, peft_adapter_path=...)`; 2.2/2.3 probe that adapter; 5.4 resolves base+adapter from the registry. Now-set acceptance (criteria 1–3) passes via `tests/test_sft.py` (7 tests; full suite 55). Deferred (GPU): 3-epoch train + eval-loss + adapter weights, sibling-dir namespacing, and the token-length measurement (1.2 jsonl not materialised yet → default 1024 retained; run `measure_token_lengths` then adjust — see decisions-log). |
| 2.2 | `2.2-diversity-penalty-sweep.md` | 2.1, 1.2, 0.2, 0.3, 0.4 | done | `experiments/probe_utils.py` (`generate_beams`, `normalised_entropy`, `roc_auc`, `covered`, `hallucinated`, `gold_patterns`) + `experiments/diversity_penalty_sweep.py` (`score_penalty`, `select_penalty`, `write_results`, `write_inference_config`, `main`). Sweeps `diversity_penalty ∈ {0.2,0.5,1.0}` with k=5 diverse beams; picks max entropy AUC under the Cov@5 ≥ 0.85 guardrail (hallucination as tiebreak), falling back + flagging if no penalty qualifies. Loads the adapter from the namespaced `checkpoints/{model_key}/sl_adapter` (deviation from spec's bare path — see decisions-log). Handoff: 2.3 reuses `probe_utils`; once the GPU sweep runs, `config/schema_linker_inference.yaml` carries the locked `diversity_penalty` that 3.1's `GenerationConfig` reads, and the recorded entropy AUC at the chosen penalty is the figure 2.3 must beat (vs ≈0.62 baseline). Now-set acceptance (criteria 1–2) passes via `tests/test_probe_utils.py` (20 tests; full suite 75). Deferred (GPU): the 125-item × 3-penalty run that writes the json table + inference YAML. |
| 2.3 | `2.3-probe-rerun.md` | 2.1, 2.2 | done | `experiments/entropy_probe.py`: three pure scorers (`h_norm_candidates` [headline, normalised candidates], `h_norm_beams` [raw], `top_beam_dominance` [`1−max_prob`]) reusing 2.2 `probe_utils` (`generate_beams`/`normalised_entropy`/`roc_auc`/`_normalise_pattern`); `compute_auc_table`, `build_finding`, `write_results`, `read_diversity_penalty` (fails clearly pointing to 2.2 if `config/schema_linker_inference.yaml`/key absent), `generate_all_beams`+`cache_beams`/`load_cached_beams` (caches `results/beams_pole.jsonl` so ablations rescore GPU-free), `main`. No code contract exported — artefact is evidence. Now-set acceptance (criterion 1: three scorers compute from hand-built beams + feed `roc_auc`) passes via `tests/test_entropy_probe.py` (15 tests; full suite 90). Deferred (GPU): the 125-item run writing `results/entropy_probe_pole.json` (AUC table vs ≈0.62 + flat-ablation finding); needs the 2.1 adapter + the 2.2-locked penalty. Two interpretive decisions logged (signal-mapping; namespaced adapter path). |
| 2.4 | `2.4-qg-training.md` | 1.3, 0.2, 2.1 *(sft.py only)* | done | `config/query_generator_train.yaml` (shared QG hyperparameters only; identical in shape to the SL YAML, differing in `data` paths → `data/ozsoy_qg_{train,eval}.jsonl`; `max_seq_length: 1024`) + `experiments/train_query_generator.py` (`--model_key`; `build_run_config` merges `config/models.yaml` registry + this YAML → namespaced `checkpoints/{model_key}/qg_adapter`; reuses `pipeline.sft.run_sft`/`build_model_inputs` from 2.1 verbatim — no QG-specific harness or masking; unknown key exits with known list). Handoff: 3.6 loads `checkpoints/{model_key}/qg_adapter` via `HuggingFaceLLM(base, peft_adapter_path=...)` paired with the matching base for greedy Cypher generation. Now-set acceptance (criteria 1–2) passes via `tests/test_train_query_generator.py` (4 tests; full suite 94). Deferred (GPU): 3-epoch train + eval-loss + adapter weights; QG token-length sub-task (1.3 jsonl not materialised → default 1024 retained, run `measure_token_lengths` then adjust — see decisions-log). **Phase 2 complete (per trained model_key).** |

## Phase 3 — Inference Components *(runtime I/O order)*

| Step | Spec file | Depends on | Status | Outputs / Handoff note |
|------|-----------|------------|--------|------------------------|
| 3.1 | `3.1-schema-linker.md` | 0.1, 0.2, 0.3, 2.1, 2.2 | not started | |
| 3.2 | `3.2-entity-lookup.md` | 0.1, 3.1 *(live Neo4j)* | not started | |
| 3.3 | `3.3-bayesian-scorer.md` | 0.1, 3.1, 3.2 | not started | |
| 3.4 | `3.4-ambiguity-detector.md` | 0.1, 0.2, 0.3, 3.1, 3.2, 3.3 | not started | |
| 3.5 | `3.5-disambiguator.md` | 0.1, 0.2, 3.1, 3.2, 3.4 | not started | |
| 3.6 | `3.6-query-generator.md` | 0.1, 0.2, 1.3, 2.4 | not started | |
| 3.7 | `3.7-cyver-validator.md` | 0.1 *(live Neo4j)* | not started | |
| 3.8 | `3.8-db-executor.md` | 0.1 *(live Neo4j)* | not started | |

## Phase 4 — Evaluation *(live Neo4j)*

| Step | Spec file | Depends on | Status | Outputs / Handoff note |
|------|-----------|------------|--------|------------------------|
| 4.1 | `4.1-semantic-evaluator.md` | 0.1 *(live Neo4j)* | not started | |
| 4.2 | `4.2-metrics.md` | 0.1, 4.1 | not started | |

## Phase 5 — Integration

| Step | Spec file | Depends on | Status | Outputs / Handoff note |
|------|-----------|------------|--------|------------------------|
| 5.1 | `5.1-components.md` | 0.1, 0.2, 3.1, 3.2, 3.6 *(live Neo4j)* | not started | |
| 5.2 | `5.2-orchestrator.md` | 3.1–3.8, 4.1, 5.1 | not started | |
| 5.3 | `5.3-condition-builders.md` | 0.2, 3.1, 3.6, 5.1 | not started | |
| 5.4 | `5.4-run-evaluation.md` | 0.3, 0.4, 4.2, 5.2, 5.3 | not started | |

## Phase 6 — Optional / Extension

| Step | Spec file | Depends on | Status | Outputs / Handoff note |
|------|-----------|------------|--------|------------------------|
| 6.1 | `6.1-prefilter.md` | 0.1 | not started | |
| 6.2 | `6.2-gradio-demo.md` | 0.3, 3.4, 3.5, 5.1, 5.2, 5.3 | not started | |

---

## Target module layout (build map)

```
pipeline/
├── types.py                         [0.1]  all shared dataclasses incl. SchemaRepr/SchemaElement
├── llm/
│   ├── base.py                      [0.2]  BaseLLM, GenerationConfig, Completion
│   ├── huggingface.py               [0.2]
│   ├── openai.py                    [0.2]
│   └── anthropic.py                 [0.2]
├── schema.py                        [0.3]  build_pole_schema_repr() + POLE constants
├── data/
│   └── benchmark_loader.py          [0.4]
├── schema_linker/
│   ├── pattern_extraction.py        [1.1]
│   ├── training_data.py             [1.2]
│   ├── prompts.py                   [1.2]  build_sl_prompt (shared train/inference)
│   ├── inference.py                 [3.1]
│   ├── postprocessing.py            [3.1]
│   └── linker.py                    [3.1]
├── query_generator/
│   ├── training_data.py             [1.3]
│   ├── prompts.py                   [1.3]  build_qg_prompt (shared train/inference/C1)
│   └── generator.py                 [3.6]
├── entity_lookup/
│   ├── registry.py                  [3.2]
│   ├── cache.py                     [3.2]
│   ├── span_extractor.py            [3.2]
│   ├── matcher.py                   [3.2]
│   └── lookup.py                    [3.2]
├── ambiguity/
│   ├── bayesian_scorer.py           [3.3]
│   ├── detector.py                  [3.4]
│   └── prompts.py                   [3.4]
├── disambiguator/
│   ├── disambiguator.py             [3.5]
│   └── prompts.py                   [3.5]
├── validation/
│   └── cyver_validator.py           [3.7]
├── execution/
│   └── db_executor.py               [3.8]
├── evaluation/
│   ├── semantic_evaluator.py        [4.1]
│   └── metrics.py                   [4.2]
├── components.py                    [5.1]
├── orchestrator.py                  [5.2]
├── sft.py                           [2.1]  build_model_inputs, run_sft (shared SL+QG harness)
└── prefilter.py                     [6.1]

experiments/
├── train_schema_linker.py          [2.1]
├── train_query_generator.py        [2.4]
├── probe_utils.py                  [2.2]  beam + entropy + AUC helpers
├── diversity_penalty_sweep.py      [2.2]
├── entropy_probe.py                [2.3]
├── build_condition1.py             [5.3]
├── build_condition2.py             [5.3]
├── build_condition3.py             [5.3]
└── run_evaluation.py               [5.4]

app/
└── gradio_demo.py                  [6.2]

config/
├── models.yaml                     [2.1]  base-model registry (key → base, target_modules, dtype, 4bit)
├── schema_linker_train.yaml        [2.1]  shared SL hyperparameters (no per-model fields)
├── schema_linker_inference.yaml    [2.2]  locked diversity_penalty for 3.1
├── query_generator_train.yaml      [2.4]  shared QG hyperparameters (no per-model fields)
└── pipeline.yaml                   [5.4]  neo4j + active_model + AD/Dis backend config

data/
└── benchmark-updated.json          [canonical, provided]

checkpoints/                        # namespaced by model_key (supports N bases)
└── {model_key}/                    # e.g. mistral7b/, llama31-8b/
    ├── sl_adapter/                 [2.1 output]
    └── qg_adapter/                 [2.4 output]
```
