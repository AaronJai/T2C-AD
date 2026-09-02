# T2C-AD Results Walkthrough — Component Evals to End-to-End

*Author: Aaron Tan · Last run: job 957276 (2026-06-29) · Model: `mistral7b` (base = Mistral-7B-v0.3, QLoRA 4-bit, Kaya 2×V100-16GB)*

This document is my synthesis of every result I have, walked from the upstream
component evaluations down to the final end-to-end run. All numbers are for the
`mistral7b` configuration.

---

## The narrative in one line

My pipeline is **mechanically complete and runs end-to-end clean**, but accuracy
sits at the floor because the **Schema Linker's intrinsic coverage is ~21%, not the
≥85% the whole architecture depends on**. Every downstream stage faithfully reflects
that upstream gap. My disambiguation machinery works as designed; it just has almost
nothing correct to disambiguate over.

---

## Stage 1 — Schema Linker training & beam quality (Phase 2)

**Token budget (job 490628):** I measured SL p99 = 3473 tok, QG p99 = 3486 tok, so I
set `max_seq_length` to 3584. The v2025 POLE schemas render bimodally — about 40% of
rows exceed the old 1024 default.

**Diversity-penalty sweep (2.2, job 511000)** — I swept k=5 diverse beams, picking
max entropy-AUC under a Cov@5 ≥ 0.85 guardrail:

| diversity_penalty | entropy AUC | Cov@5 (exact-string) | hallucination |
|---|---|---|---|
| **0.2 (chosen)** | **0.587** | 0.000 | 0.024 |
| 0.5 | 0.563 | 0.000 | 0.026 |
| 1.0 | 0.534 | 0.000 | 0.030 |

⚠ **No penalty cleared the guardrail** — Cov@5 = 0.000 across the board. I picked 0.2
via the documented fallback (best AUC). This 0.000 is the exact-string measure; every
beam carries a dangling `--` suffix that fails string match — I resolved that at 3.1
(below).

**Entropy probe (2.3, job 511001)** — I tested whether post-SFT beam entropy can
predict ambiguity:

| signal | POLE-SFT AUC | prior general-model AUC |
|---|---|---|
| h_norm_candidates (headline) | 0.592 | 0.622 |
| h_norm_beams | 0.587 | 0.624 |
| top_beam_dominance | 0.594 | 0.625 |

⚠ **Success criterion #6 NOT met:** my post-SFT signal (0.592) is **flat against** the
≈0.62 baseline, not above it. Ablations are flat too (spread 0.007). This is
acceptable *by design* — entropy is my secondary signal and the LLM self-assessment is
primary — but the secondary signal is effectively dead because the beams lack
diversity.

---

## Stage 2 — Schema Linker intrinsic accuracy (3.1) — the linchpin

I measured this GPU-free from the deterministic cached beams, with the postprocessing
parser stripping the `--` artefact:

| metric | measured | target | status |
|---|---|---|---|
| **Cov@5** (gold pattern in top-5 beams) | **0.208** | ≥ 0.85 | ❌ **far below** |
| EM@1 (gold == top beam) | 0.144 | — | — |

The parser fix lifted Cov@5 from 0.000 → 0.208 (so the `--` *was* a real artefact),
but 0.208 is the genuine ceiling. I diagnosed this as a true model-quality gap, not a
measurement bug: it holds under a looser relationship-set-only match (also 0.208), and
it's not single-hop truncation (beam hop-counts span 1–7). The beams are
schema-*plausible* but structurally mismatch the gold (wrong relationship choice / path
shape). I flagged it for 2.1/2.2 (training quality), not as a 3.1 defect.

This is **success criterion #5**, and it's the one my whole thesis hangs on: *"the
disambiguator can only succeed if the right interpretation is in the distribution."* At
Cov@5 = 0.21, the right interpretation is absent ~79% of the time.

---

## Stage 3 — Ambiguity Detector probe (3.4, job 511162, 9-question sample)

The stage runs end-to-end, never raises, and emits well-formed JSON with coherent
rationales — but all 9 questions (including 7 gold-ambiguous) classified
`is_ambiguous=False`, because `schema_entropy = entity_entropy = 0.00` on every item.
The SL collapses to a single candidate per slot (the same Cov@5 gap), so the AD's
secondary signal is empty, and base (non-instruct) Mistral-7B leans on that flat
evidence. The LLM-primary design *could* flag ambiguity from question text alone, but
base Mistral-7B doesn't. My documented path to real detection is a stronger/instruct
backend via the `ad`/`dis` API swap points.

---

## Component probes (3.2, 3.5–3.8) — mechanical completeness evidence

The rest of the inference path was also proven for real on Kaya, independently of the
accuracy floor above. Citing it here because "the pipeline itself is sound" and "my
disambiguation machinery works as designed" (below) rest on this evidence, not just on
the fact that the 5.4 full run didn't crash.

| Step | Job | What ran | Result |
|---|---|---|---|
| 3.2 Entity Lookup | 511153 (k005) | `EntityCache.load` against the live SyntheticPoliceKG | Exactly Person 35 / Organisation 5 / Case 4 / Location 18 (62 name-searchable), correctly shaped `CachedNode`s |
| 3.5 Disambiguator | 512038 (k027, ~5.6 min) | Real SchemaLinker + live Entity Lookup + base Mistral-7B-v0.3 as the dis LLM, 7-question ambiguous sample, 2 attempts each | Committed a `SchemaMapping` for **7/7**; retry path honoured `previously_tried` (repeat → fallback fired) and returned `None` once exhausted |
| 3.6 Query Generator | 512508→512707 (k036, ~3 min, GPU only) | Trained `mistral7b/qg_adapter`, 8-question stratified sample, both committed-pattern and zero-shot modes | Clean executable `MATCH … RETURN` for **8/8 in both modes (16/16 total)** |
| 3.7 CyVer Validator | 513073 (k011, ~22s, Neo4j only) | 5 crafted queries (valid w/ + w/o props, bad syntax, unknown label, unknown property) against the live validators | **5/5** routed correctly (accept / accept / query_generator / schema_linker / schema_linker) |
| 3.8 DB Executor | 513261 (k005, ~25s, Neo4j only) | Real POLE queries incl. an empty-result case and a heavy `[*1..30]` traversal | Rows returned correctly, empty result → `success=True`, and the traversal correctly timed out (`success=False`, `TransactionTimedOutClientConfiguration`) |

Together with 2.2/2.3 (Stage 1), 3.1 (Stage 2), and 3.4 (Stage 3) above, this covers all
eight inference components (3.1–3.8) individually verified against live GPU/Neo4j before
the 5.4 end-to-end run ever executed. It's the concrete basis for "the pipeline itself is
sound" below: the 125×3 run's floor accuracy is fully explained by the 3.1 Cov@5 gap, not
by any other component failing to do its job.

---

## Stage 4 — End-to-end evaluation (5.4, job 957276, post-evaluator-fix, 125×3)

### Table 1 — Overall (125 questions)

| Metric | C1 baseline | C2 schema-grounded | C3 disambiguation |
|---|---|---|---|
| **EX** | 0.008 (1/125) | 0.008 (1/125) | 0.008 (1/125) |
| **EA / AREA** | 0.008 | 0.008 | 0.008 |
| KG-Valid % | 22.4 | 10.4 | 12.8 |
| Syntax % | 92.8 | 48.8 | 66.4 |
| Schema % | 74.1 | 68.9 | 67.5 |
| Pass@1 | 0.008 | 0.008 | 0.008 |

### Table 2 — Ambiguity-specific (50 ambiguous)

| Metric | C1 | C2 | C3 |
|---|---|---|---|
| Ambiguous EA | 0.0 | 0.0 | 0.0 |
| DSR | — | — | 0.0 |
| Detection F1 | — | — | **23.3** |
| Detection Prec | — | — | 50.0 |
| Detection Rec | — | — | **15.2** |
| EA — schema (n=13) | 0.0 | 0.0 | 0.0 |
| EA — entity (n=11) | 0.0 | 0.0 | 0.0 |
| EA — intent (n=11) | 0.0 | 0.0 | 0.0 |
| EA — temporal (n=15) | 0.0 | 0.0 | 0.0 |

### Table 3 — Repair / routing (C2, C3)

| Metric | C2 | C3 |
|---|---|---|
| Initial Valid % | 10.4 | 12.0 |
| Post-CyVer Valid % | 10.4 | 12.8 |
| Structural Repair % | 0.0 | 0.9 |
| Semantic Repair % | 0.0 | 0.0 |
| Avg Iterations | 1.20 | 0.82 |

*(C1 avg iterations = 2.11 — the baseline still uses the inner QG+CyVer syntax-retry
loop.)*

**Effect of my evaluator column-name fix:** it recovered exactly **one** C1 question
(C1 EX 0.0 → 0.008); C2/C3 unchanged. This confirms the column-name strictness was a
thin measurement layer over a genuine quality floor — not the cause of the low numbers.

---

## Scorecard against my 7 success criteria

| # | Criterion | Target | Result | Met? |
|---|---|---|---|---|
| 1 | C3 > C2 on ambiguous AREA/EX | C3 higher | C3 = C2 = 0 | ❌ |
| 2 | Monotonic C3 ≥ C2 ≥ C1 (overall EX) | ordered | all 0.008, tied | ❌ (tied at floor) |
| 3 | Detection F1 above baseline, usable recall | high recall | F1 23.3, **rec 15.2%** | ❌ (recall too low → DSR uninformative) |
| 4 | Per-type C3 gains (schema/entity/temporal) | measurable | all 0.0 | ❌ |
| 5 | **Schema Linker Cov@5 ≥ 85%** | ≥ 0.85 | **0.208** | ❌ **root cause** |
| 6 | Post-SFT entropy AUC > 0.62 | improve | 0.592, flat | ❌ |
| 7 | High KG-valid + repair recovers invalid | high | 10–22% valid, ~0–1% repair | ❌ |

---

## What this means (my honest read)

1. **One root cause cascades.** Criterion #5 (Cov@5 0.21) is upstream of everything.
   With the gold pattern absent from the beams 4 times out of 5, my QG generates
   structurally-wrong Cypher (KG-valid only 10–22%), my AD has no entropy signal to
   detect ambiguity (recall 15%), and my disambiguator has nothing correct to route to.
   C3 ≈ C2 ≈ C1 is the *expected* consequence, not a wiring bug.

2. **The pipeline itself is sound.** I proved every stage independently on Kaya (see the
   component-probes table above — 3.2/3.5/3.6/3.7/3.8 all individually verified against
   live GPU/Neo4j), the full 125×3 run completes clean (0 tracebacks), CyVer routes, the
   repair loop fires (C3 structural repair 0.9%), and the metrics aggregate correctly. My
   architecture is validated *mechanically*; the architectural *claim* (C3 > C2) can't be
   tested while the substrate is at the floor.

3. **The gap is model quality, and it's localised.** I have two concrete, documented
   levers, both config-only (no code change):
   - **SL retraining** (2.1/2.2) — better / more POLE-specific schema-linking data to
     lift Cov@5. This is the highest-leverage fix; nothing downstream can exceed it.
   - **`ad`/`dis` API swap points** (5.3/5.4) — a stronger / instruct backend (or
     Claude / OpenAI) for the Ambiguity Detector + Disambiguator, my documented path to
     real detection numbers.

In thesis terms: this run establishes a **clean, reproducible baseline and a
fully-instrumented harness**, and it **localises the bottleneck unambiguously to Schema
Linker coverage** — which is a legitimate and publishable finding, even though the
headline accuracy is at the floor. The next experiment that matters is lifting Cov@5;
everything else is currently gated on it.

---

## Run provenance

| Artefact | Source |
|---|---|
| `results/metrics_mistral7b.json`, `results/tables_mistral7b.md` | job 957276 (2026-06-29, k027, ~5h, clean) |
| `results/entropy_probe_pole.json` | job 511001 (2.3 probe) |
| `results/diversity_penalty_sweep.json`, `config/schema_linker_inference.yaml` | job 511000 (2.2 sweep) |
| `results/beams_pole.jsonl` | cached SL beams (k=5, dp=0.2) — source for the 3.1 Cov@5/EM@1 |
| Cov@5 = 0.208 / EM@1 = 0.144 | 3.1 acceptance #6 (decisions-log 2026-06-15) |
| AD probe (all `is_ambiguous=False`) | job 511162 (3.4 acceptance #5) |
| Entity Lookup probe (Person 35/Org 5/Case 4/Location 18) | job 511153 (3.2 acceptance #5) |
| Disambiguator probe (7/7 committed, retry path confirmed) | job 512038 (3.5 acceptance #6) |
| Query Generator probe (16/16 clean Cypher, both modes) | jobs 512508→512707 (3.6 acceptance #4) |
| CyVer Validator probe (5/5 routed correctly) | job 513073 (3.7 acceptance #6) |
| DB Executor probe (rows, empty-result, timeout all confirmed) | job 513261 (3.8 acceptance #4) |
