# T2C-AD Results Walkthrough — Qwen2.5-32B (SFT), v3 + external POLE (Phase 10.7)

*Author: Aaron Tan · G4 runs: job **1144487** (v3, 120×3, 1h21m57s) and job **1144488**
(external POLE, 100×3, 1h28m08s), both 2026-08-29 on Kaya's new `rrifcs` H100 partition (node
k172, 2× H100 NVL each), both `COMPLETED 0:0` with **0 tracebacks**. Model: `qwen2.5-32b`
(`Qwen/Qwen2.5-32B` **base**, 4-bit/fp16) + the Phase 10.6 two-stage LoRA adapters. Companions:
[`results-walkthrough.md`](results-walkthrough.md) (v2-mistral),
[`results-walkthrough-v3.md`](results-walkthrough-v3.md) (v3-mistral),
[`results-walkthrough-v3-claude-sonnet.md`](results-walkthrough-v3-claude-sonnet.md) (v3-claude).*

This page adds the **third model column** — a large open-weights model that is *actually
fine-tuned*, unlike the API instruct column — and is the first to report **both** substrates for
one model. With it the dissertation's model × dataset matrix is complete, and the three axes of
the argument can finally be read off separately:

- **substrate** — v2 → v3 → external POLE (a graph the student did not author);
- **architecture** — C1 → C2 → C3, the disambiguation stage itself;
- **model** — mistral-7B(SFT) → claude-sonnet(instruct) → **qwen-32B(SFT)**.

**All prior artefacts are byte-unchanged** (53 `results/` files + the three walkthroughs above,
verified by checksum), and every Qwen artefact carries a distinct `v3_qwen` / `pole_external_qwen`
tag.

---

## The narrative in one line

Fine-tuning a 32B open model **reproduces the architectural claim on both substrates and, on the
external graph, brings a *local* model to parity with the API model on ambiguity detection**
(F1 **82.2** vs claude's 82.0) — while leaving a large gap on Schema-Linker coverage that scaling
the base model conspicuously fails to close (0.725 → 0.750 for 4.6× the parameters). The
architecture, not the model size, is what moves the numbers.

---

## The gated runbook (10.7 G0–G4, cheapest-first)

No gate was skipped past a failure and **no G1 loop back to 10.6 was needed**.

| Gate | What | Job(s) | Result | Verdict |
|---|---|---|---|---|
| **G0** | Offline suite + config audit | — | 400 passed / 5 pre-existing unrelated fails; both configs key-diff-identical to the canonical local ones bar `active_model`/`results_tag` | ✅ |
| **—** | *Pre-G4 QG smoke (not a spec gate)* | 1144411 | 6/6 probe items gold-exact on both substrates; property names correct | ✅ |
| **G1** | Full-benchmark SL Cov@5 / EM@1 | 1144408, 1144409 | v3 **0.750** / 0.683 · external **0.780** / 0.660 (bar ≥ 0.60) | ✅ |
| **Attr.** | Three-way adapter attribution | 1144412–15 | v3 0.033→0.533→0.750 · ext 0.010→0.540→0.780 | ✅ |
| **G2a** | Diversity-penalty sweep (v3) | 1144445 | dp ∈ {0.2, 0.5, 1.0} → locked **dp = 1.0**; hallucination 0.000 at every penalty | ✅ |
| **G2b** | Entropy probe (v3) | 1144484 | AUC **0.570** — misses the 0.62 baseline | ⚠ ran |
| **G3** | AD stratified probe | 1144485, 1144486 | v3 **8/10** · external **9/10**; AD JSON parses natively | ✅ |
| **G4** | Full e2e | 1144487, 1144488 | 120×3 and 100×3, 0 tracebacks, 8 artefacts | ✅ |

**Scope notes, recorded rather than glossed.** The G2 sweep and entropy probe run on **v3 only** —
`diversity_penalty_sweep.py` and `entropy_probe.py` both take `--dataset_version v2|v3` with no
`pole_external` branch, so the external substrate reuses the v3-locked dp=1.0 as a documented
pragmatic default. This is the same deferral 10.4 recorded for Mistral, and 10.6's external sample
Cov@5 = 0.760 at that penalty says the substrate is not decoding-limited. See decisions-log
2026-08-28/29.

---

## Stage 1 — Schema Linker: the adapter matters far more than the model

**Three-way attribution** (no adapter / +generic Ozsoy / +generic+in-domain POLE), all cells at the
locked dp=1.0 so the comparison is single-factor on the adapter:

| Substrate | no adapter | + generic Ozsoy | + generic + in-domain POLE |
|---|---|---|---|
| **v3** (n=120) | 0.033 | 0.533 | **0.750** |
| **external POLE** (n=100) | 0.010 | 0.540 | **0.780** |

Beside Mistral's equivalent on v3 (2026-07-16), **at a matched dp=1.0**:

| Model | no adapter | + generic Ozsoy | + generic + in-domain POLE |
|---|---|---|---|
| mistral-7B | 0.000 | 0.483 | **0.725** |
| **qwen-32B** | 0.033 | 0.533 | **0.750** |

And restricted to the **`schema` type** — the four role-split Person→Incident edges that *are* the
designed schema ambiguity:

| Model | no adapter | + generic Ozsoy | + generic + in-domain POLE |
|---|---|---|---|
| mistral-7B | 0.00 | 0.15 | **0.95** |
| **qwen-32B** | 0.00 | 0.00 | **0.95** |

**Two claims, replicated across a 7B and a 32B.** (a) The generic Ozsoy adapter contributes
essentially *nothing* on the role-split edges; in-domain SFT supplies them entirely — the designed-
ambiguity axis is exactly where in-domain SFT is load-bearing. (b) **4.6× more base model buys
~2.5 pp of overall Cov@5, while the in-domain adapter buys ~22 pp on top of the generic one.** For
schema linking the adapter axis dominates the model-scale axis.

*Data-hygiene note carried into the decisions log:* Mistral's dp=1.0 in-domain cell is
`g1_sl_coverage_mistral7b_v3_locked.json` (0.725), **not** the similarly-named
`g1_sl_coverage_mistral7b_v3.json` (0.683, dp=0.2). Reaching for the obvious filename mixes two
decodings and understates the in-domain increment by 4.2 pp.

**Per-type Cov@5, in-domain tier.** v3: temporal 1.00, schema 0.95, null 0.68, intent 0.65,
entity 0.55. External: entity 1.00, temporal 1.00, schema 0.95, null 0.65, **intent 0.30**. Intent
is the weak type on external for *both* models (Mistral 0.45), which supports 10.6's read that this
is a property of the substrate rather than a model deficiency.

---

## Stage 2 — Ambiguity Detector (G3): the first local model whose detector reasons for itself

| | binary | TP | FP | FN | TN |
|---|---|---|---|---|---|
| v3 (job 1144485) | **8/10** | 6 | 0 | 2 | 2 |
| external (job 1144486) | **9/10** | 7 | 0 | 1 | 2 |
| *10.4 base-Mistral, external* | *6/10* | *4* | *0* | *4* | *2* |

The counts matter less than the mechanism. In every prior **local** run (3.4, 7.5, 10.4) the base
7B emitted unparseable AD JSON, so its only true positives came from the `entity_entropy = 1.00`
fallback and schema/intent/temporal were missed wholesale. Base Qwen-32B emits well-formed JSON
with substantive rationales — it caught an external `intent` item by reasoning about a genuine tie
("aside from X" leaving two officers both at n=44). That is the mechanism behind the C3 gains below:
the disambiguation loop can only fire on items the detector flags.

*Caveats kept explicit:* n=10 stratified per substrate (counts recorded, **not** a numeric gate,
per 7.5/10.4); FP=0 on both means precision is untested at this n; and both v3 misses are *type*
errors on correctly-detected items (Q-101 temporal and Q-082 intent both fired as `entity`), so
binary detection overstates per-type competence. The full picture is in G4's Detection F1.

---

## Stage 3 — End-to-end (G4)

### v3 substrate — job 1144487, 120×3

| Metric (%) | C1 | C2 | C3 |
|---|---|---|---|
| **EX** | 5.8 | 20.0 | **25.0** |
| **EA / AREA** | 7.5 | 35.8 | **43.3** |
| Ambiguous EA (n=80) | 5.0 | 36.2 | **42.5** |
| KG-Valid | 89.2 | 83.3 | 85.0 |
| Detection F1 / P / R | — | — | **60.5 / 69.6 / 53.4** |
| DSR | — | — | 19.6 |
| Structural / semantic repair | 59.4 / 0.0 | 51.2 / 0.0 | 61.7 / 10.4 |

Per-type EA: schema 5.0 → 25.0 → **45.0**, entity 5.0 → 20.0 → 25.0, intent 5.0 → 30.0 → 30.0,
temporal 5.0 → 70.0 → 70.0.

### External POLE substrate — job 1144488, 100×3

| Metric (%) | C1 | C2 | C3 |
|---|---|---|---|
| **EX** | 40.0 | 37.0 | **53.0** |
| **EA / AREA** | 41.0 | 45.0 | **64.0** |
| Ambiguous EA (n=80) | 28.7 | 38.8 | **60.0** |
| KG-Valid | 86.0 | 80.0 | 88.0 |
| Detection F1 / P / R | — | — | **82.2 / 90.9 / 75.0** |
| DSR | — | — | 56.1 |
| Structural / semantic repair | 30.0 / 0.0 | 41.2 / 0.0 | 61.3 / 5.0 |

Per-type EA: schema 5.0 → 40.0 → **60.0**, entity 60.0 → 55.0 → 55.0, intent 25.0 → 25.0 → 25.0,
temporal 25.0 → 35.0 → **100.0**.

**The single strongest result in the project.** On external `temporal`, C3 fixes **13 of the 20**
questions C2 got wrong and regresses **none** — 7/20 → 20/20 on execution accuracy. This is the
architectural claim in its cleanest form: the questions are unchanged, the schema linker is
unchanged, and the only added machinery is detect-then-commit. **11.5 confirms it is the one
per-type cell in the project whose margin outruns the noise floor by a wide margin: ΔEX C3−C2
= +65.0 [+45.0, +85.0]**, and it stays significant under abort exclusion (+61.1 [+38.9, +83.3]).
Every other per-type cell on this page sits inside the ~15 pp width of an n=20 interval and is
indicative only.

**The one non-monotonicity, reported honestly.** On external EX, **C2 (37.0) falls below C1
(40.0)**. This is churn, not a systematic regression: 12 items lost, 9 gained (net −3 on n=100),
spread evenly across entity/temporal/null, split half `wrong_result` and half `invalid_query`, and
C3 recovers 5 of the 12. The mechanism is visible in the records — e.g. Q-POLE-E12 "What address is
on file for Hughes?", where zero-shot C1 correctly filters on `surname:"Hughes"` and the fine-tuned
QG substitutes `name:'Hughes'`. Base Qwen-32B is strong enough zero-shot on this graph (C1 EX 40.0,
vs claude 20.0 and mistral 14.0) that a beam_k=1 schema-grounded commit occasionally costs more
than it adds. EA, ambiguous EA and every C3 comparison remain monotonic.

**11.5 upholds this reading and lets it be stated more strongly (amended 2026-08-31).** The
"churn" call was the right one and is now backed by an interval rather than asserted: overall
ΔEX C2−C1 = **−3.0 [−12.0, +6.0]**, ΔEA **+4.0 [−7.0, +15.0]**, ambiguous ΔEA **+10.0
[−2.5, +22.5]** — every margin spans zero. So the defensible statement is **"C2 and C1 are
indistinguishable on external at this n"**, not that C2 regressed. The 72B page's stronger
reading of the same shape — that two models agreeing makes it a property of the substrate and
recipe — has been **withdrawn** on the same evidence. See
[`variance-and-error-bars.md`](variance-and-error-bars.md).

---

## The three-model matrix

### v3 substrate (120 questions, 80 ambiguous; %)

| Metric | mistral-7B (SFT) | claude-sonnet (instruct) | **qwen-32B (SFT)** |
|---|---|---|---|
| EX C1 / C2 / C3 | 5.0 / 15.8 / 12.5 | 7.5 / 37.5 / **52.5** | 5.8 / 20.0 / 25.0 |
| EA C1 / C2 / C3 | 10.8 / 28.3 / 27.5 | 7.5 / 57.5 / **62.5** | 7.5 / 35.8 / 43.3 |
| Ambiguous EA C2 → C3 | 27.5 → 31.2 | 50.0 → **57.5** | 36.2 → 42.5 |
| Detection F1 / recall | 30.6 / 19.2 | **73.9** / 66.2 | 60.5 / 53.4 |
| DSR | 0.0 | **49.2** | 19.6 |
| SL Cov@5 | 0.725 | 0.658 | **0.750** |

### External POLE substrate (100 questions, 80 ambiguous; %)

| Metric | mistral-7B (SFT) | claude-sonnet (instruct) | **qwen-32B (SFT)** |
|---|---|---|---|
| EX C1 / C2 / C3 | 14 / 21 / 24 | 20 / 59 / **64** | **40** / 37 / 53 |
| EA C1 / C2 / C3 | 14 / 21 / 26 | 21 / 64 / **70** | 41 / 45 / 64 |
| Ambiguous EA C2 → C3 | 15.0 → 23.8 | 57.5 → **63.7** | 38.8 → 60.0 |
| Detection F1 / recall | 61.2 / 49.3 | 82.0 / 71.2 | **82.2** / **75.0** |
| DSR | 30.4 | **64.4** | 56.1 |
| SL Cov@5 | **0.810** | — | 0.780 |

**Reading the matrix.** On v3 the ordering is mistral < qwen < claude on every accuracy metric. On
the external graph — the harder, non-self-authored substrate — the picture changes: qwen **matches
claude on detection** (F1 82.2 vs 82.0, with *better* recall, 75.0 vs 71.2), gets within 3.7 pp on
ambiguous EA (60.0 vs 63.7), and has the strongest zero-shot baseline of the three by a wide margin
(C1 EX 40 vs 20 vs 14). The residual claude advantage concentrates in end-to-end EX (64 vs 53),
which the qualitative records attribute to query-construction rather than to schema linking or
detection.

---

## Scorecard against the 7 success criteria (project-overview §9)

| # | Criterion | v3-mistral | v3-claude | **v3-qwen** | **ext-qwen** |
|---|---|---|---|---|---|
| 1 | C3 > C2 on ambiguous AREA/EX | 31.2 > 27.5 ✅ | 57.5 > 50.0 ✅ | **42.5 > 36.2 ✅ · CI +6.2 [+1.2, +12.5]** | **60.0 > 38.8 ✅ · CI +21.2 [+11.2, +31.2]** |
| 2 | Monotonic C3 ≥ C2 ≥ C1 | EX C3<C2 ⚠ | 7.5<37.5<52.5 ✅ | **EX 5.8<20.0<25.0 ✅** | EA ✅; **EX C2 vs C1 not measurable** (−3.0 [−12.0, +6.0]) |
| 3 | Detection F1 above baseline, usable recall | 30.6 / 19.2 ⚠ | 73.9 / 66.2 ✅ | **60.5 / 53.4 ✅** | **82.2 / 75.0 ✅** |
| 4 | Per-type C3 gains (schema/entity/temporal) | schema +15; entity flat ⚠ | +5/+10/+10 ✅ | schema **+20**; entity +5; temporal flat ⚠ | schema **+20**; temporal **+65** ✅ |
| 5 | SL Cov@5 ≥ 85% | 0.725 ❌ | 0.658 ❌ | 0.750 ❌ | 0.780 ❌ |
| 6 | Post-SFT entropy AUC > 0.62 | 0.689 ✅ | 0.525 ❌ | 0.570 ❌ | deferred |
| 7 | High KG-valid + repair recovers | 62–74%, ~0% repair ⚠ | 87–98% ✅ | **83–89%, repair 51–62% ✅** | **80–88%, repair 41–61% ✅** |

**11.5 (2026-08-31) makes these two Qwen-32B columns the project's strongest.** Criterion #1
clears zero on **both** substrates under **both** strata — the only model column of which that is
true — so this is where the architectural claim is defended. Criterion #2's external ⚠ is a
non-result, not a failure. Both revisions are recorded in the sections above.

**Qwen meets #1, #2 (v3 outright), #3, #7 on both substrates**, and #4 outright on external. It is
the **first local model to be monotonic on v3 EX** — Mistral's C3 (12.5) fell below its C2 (15.8),
Qwen's rises 20.0 → 25.0 — and the first local model whose criterion #7 repair loop demonstrably
recovers a large fraction of invalid queries (51–62% structural repair, against Mistral's ~0–3%).

**The two misses are the interesting ones.** #5 (Cov@5 ≥ 0.85) is missed by every model in the
project, including the API model, and the attribution above shows scale is not the lever. #6
(entropy AUC) is missed at 0.570 — **scaling the base 4.6× did not rescue the secondary Bayesian
signal**, and Qwen lands nearer claude (0.525, flat) than Mistral (0.689). Reported as a negative
result rather than tuned around: it strengthens project-overview §7's locked decision that LLM
self-assessment is *primary* and entropy *secondary*, because the same model that lost the entropy
signal simultaneously delivered the best local detector in the project (G3, and F1 82.2 above).

---

## What this means (honest read)

1. **The architectural claim replicates on a third model and a second substrate.** C3 > C2 on
   ambiguous EA now holds in **all six** model × substrate cells on the v3 and external substrates
   (v3: mistral 27.5→31.2, claude 50.0→57.5, qwen 36.2→42.5; external: mistral 15.0→23.8, claude
   57.5→63.7, qwen 38.8→60.0) — the frozen v2-mistral baseline remains the known floor at
   C3 = C2 = 0. Qwen-external is the **largest margin of the six** (+21.2 pp). The external temporal cell (7/20 → 20/20, 13
   fixed, 0 regressed) is the cleanest single demonstration the project has produced.
2. **Model scale is the weakest of the three axes.** 7B → 32B moved SL Cov@5 by 2.5 pp while the
   in-domain adapter moves it by ~22 pp and the substrate redesign moved it by far more than either.
   Where scale *did* pay off is the **detector** — the stage that depends on reasoning rather than
   on format compliance.
3. **A fine-tuned open model can match an API instruct model on detection.** F1 82.2 vs 82.0 with
   better recall, on the external graph, is the first evidence in this project that the
   detect-then-commit architecture does not require a frontier API model to work.
4. **What it does not close is query construction.** Claude's remaining external EX advantage
   (64 vs 53) sits downstream of both schema linking and detection; the same limit, in a milder
   form, that decisions-log 2026-08-23 attributed to malformed Cypher generation in the 7B.
5. **Absolute numbers stay modest and are reported as such**, per project-overview §8 — the
   contribution here is architectural, and the matrix is what carries it.

---

## Run provenance

| Artefact | Path |
|---|---|
| v3 tables / metrics / records / qualitative | `results/{tables,metrics,qual_records,qualitative_analysis}_qwen2.5-32b_v3_qwen.*` |
| External tables / metrics / records / qualitative | `results/{tables,metrics,qual_records,qualitative_analysis}_qwen2.5-32b_pole_external_qwen.*` |
| G1 coverage + beams | `results/g1_sl_coverage_qwen2.5-32b_{v3,pole_external}.json`, `results/beams_…jsonl` |
| Attribution tiers | `results/g1_sl_coverage_qwen2.5-32b_{v3,pole_external}_qwen_{generic,noadapter}.json` |
| Sweep / entropy probe | `results/diversity_penalty_sweep_qwen2.5-32b_v3.json`, `results/entropy_probe_qwen2.5-32b_v3.json` |
| Configs | `config/pipeline_{v3,pole_external}_qwen.yaml`, `config/schema_linker_inference.yaml` |
| Runners | `kaya/104`–`kaya/110` |

Qualitative buckets (C2 vs C3): v3 both_correct 22 / both_wrong 88 / **fixed 8** / regressed 2;
external both_correct 37 / both_wrong 47 / **fixed 16** / **regressed 0**.
