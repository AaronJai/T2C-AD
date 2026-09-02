# T2C-AD Results Walkthrough — v3 Substrate (Phase 7.5 staged revalidation)

*Author: Aaron Tan · v3 E2E: job 1065123 (2026-07-17) · Model: `mistral7b` (base = Mistral-7B-v0.3,
QLoRA 4-bit, Kaya 2×V100-16GB) · Compare against the frozen v2 baseline (job 957276) in
[`results-walkthrough.md`](results-walkthrough.md).*

> **Third column (Phase 8):** the same pipeline on the same v3 substrate with a strong instruct
> API model (Claude Sonnet 4.6) is written up in
> [`results-walkthrough-v3-claude-sonnet.md`](results-walkthrough-v3-claude-sonnet.md) — it closes
> the "stronger AD/Dis backend" thread (Detection F1 30.6 → 73.9) that this run left open.

This is the v3 companion to the v2 walkthrough. The v2→v3 before/after runs on **identical pipeline
code** — the delta is entirely in the *substrate*. So this comparison is the dissertation's
**substrate-vs-architecture** argument: the pipeline design is not the bottleneck once the substrate
improves.

**"Substrate" means two separable interventions, not one**, and the distinction is load-bearing:
the concise 6-label/11-relationship schema + rebuilt 120-question benchmark, **and** Phase 7.4's
in-domain POLE SFT (`{sl,qg}_adapter_v3`) — which never existed for v2, whose frozen adapters are
zero-shot on POLE entirely. An ablation running the untouched pre-7.4 adapters against the v3 schema
separates them (Stage 1): **both are real and roughly comparable in size**, neither sufficient
alone. The claim this doc supports is therefore "**the architecture was never the bottleneck; the
substrate was, and it has two levers**" — not "one substrate swap did it".

---

## The narrative in one line

Fixing the substrate lifted the Schema Linker off the floor (**Cov@5 0.208 → 0.725**), which
propagated all the way down: the entropy signal moved above its baseline for the first time
(**AUC 0.592 → 0.689**), end-to-end accuracy rose an order of magnitude (**EA 0.008 → 0.283**),
and — the load-bearing result — **disambiguation now adds measurable value on the ambiguous
subset (C3 31.2% > C2 27.5% AREA; schema-type 35% > 20%)**. The architectural claim, untestable
at v2's floor, is now demonstrable.

A second, separate finding: the Query Generator was the only stage never shown the schema's
**Properties** list — a defect, not a design choice. Fixing it improves every condition on every
metric (EA C1 4.2→10.8, C2 23.3→28.3, C3 23.3→27.5) and removes a fairness confound against the API
column, but does **not** close the gap to claude-sonnet (C2 EA 28.3 vs 57.5). All numbers in this
doc are the properties-on run; the properties-off arm is reported as its ablation.

---

## The gated runbook (7.5 G0–G4, cheapest-first)

Each gate was a go/no-go; none was skipped past a failure.

| Gate | What | Job | Result | Verdict |
|---|---|---|---|---|
| **G0** | Offline suite + benchmark validation on live v3 graph | 1032327 | 294 tests pass; all 8 gates green | ✅ |
| **G1** | SL intrinsic Cov@5/EM@1, all 120 q, pre-sweep dp=0.2 | 1032328 | **Cov@5 0.683 / EM@1 0.667** | ✅ ≥0.60 |
| **G2a** | 2.2 diversity-penalty sweep (re-lock dp) | 1032339 | dp **1.0** chosen (Cov@5 0.725, AUC 0.682) | ✅ (fallback) |
| **G2b** | 2.3 entropy probe at locked dp | 1032344 | headline AUC **0.689 > 0.62** | ✅ crit #6 |
| **G3** | 3.4-style AD stratified probe (base LLM) | 1032391 | non-zero entropies now live (entity 1.00) | ✅ |
| **G4** | Full 120×3 end-to-end | 1065123 | Tables 1–3 below (clean, 0 tracebacks) | ✅ |

---

## Stage 1 — Schema Linker coverage & beam quality (G1, G2)

**Diversity-penalty sweep (G2a, job 1032339)** — swept k=5 diverse beams over all 120 v3
questions with `sl_adapter_v3`:

| diversity_penalty | entropy AUC | Cov@5 | hallucination |
|---|---|---|---|
| 0.2 | 0.649 | 0.683 | 0.007 |
| 0.5 | 0.649 | 0.692 | 0.007 |
| **1.0 (chosen)** | **0.682** | **0.725** | 0.003 |

No penalty cleared the Cov@5 ≥ 0.85 guardrail, so selection took the documented fallback (best
Cov@5/AUC trade-off) — but 1.0 wins on **both** axes, a clean choice (contrast v2, where all three
penalties sat at Cov@5 0.000 and the fallback picked the least-bad AUC). `diversity_penalty: 1.0`
is now locked in `config/schema_linker_inference.yaml`.

**Intrinsic Cov@5 / EM@1 at the locked decoding (dp=1.0):**

| type | n | Cov@5 | EM@1 |
|---|---|---|---|
| schema | 20 | 0.950 | 0.850 |
| entity | 20 | 0.450 | 0.450 |
| intent | 20 | 0.550 | 0.450 |
| temporal | 20 | 1.000 | 1.000 |
| null | 40 | 0.700 | 0.625 |
| **overall** | **120** | **0.725** | **0.667** |

Cov@5 0.725 is **3.5× v2's 0.208** but still short of the 0.85 target (criterion #5). The residual
is concentrated in **entity (0.45)** and **intent (0.55)**: entity misses are usually a missing
`{active:true}` temporal qualifier the gold requires; intent is acknowledged as the hardest type.
schema (0.95) and temporal (1.00) — the types the 7.4 schema-connector register targeted — are
essentially solved intrinsically.

**Entropy probe (G2b, job 1032344, at dp=1.0):**

| signal | POLE-SFT v3 AUC | prior general-model AUC | v2 POLE-SFT AUC |
|---|---|---|---|
| **h_norm_candidates (headline)** | **0.689** | 0.622 | 0.592 |
| h_norm_beams | 0.682 | 0.624 | 0.587 |
| top_beam_dominance | 0.661 | 0.625 | 0.594 |

**Criterion #6 met for the first time:** the headline signal (0.689) clears the ~0.62 baseline.
And unlike v2 — where ablations were dead flat (spread 0.007) because the beams had no diversity —
v3's ablations are **not flat (spread 0.028 > 0.01)**: the scoring function now discriminates,
which is only possible because the beams genuinely spread across schema candidates. This directly
confirms the correlation hypothesis from the v2 post-mortem ("if beam diversity is real, entropy
AUC should move off the floor"). It did.

**Attribution ablation — schema redesign vs. Phase 7.4 in-domain SFT (decisions-log 2026-07-16).**
v2's Cov@5 (0.208) and v3's Cov@5 (0.725) differ in two things at once: the schema/benchmark and
the training data (Phase 7.4 in-domain SFT never existed for v2). To separate them, the untouched
pre-7.4 checkpoints (`checkpoints/mistral7b/sl_adapter`, generic-Ozsoy-only — no POLE exposure at
all) were run zero-shot against the **v3** schema/benchmark, no new training required:

| Schema | Training | Cov@5 |
|---|---|---|
| v2 (28 rel types, lexical noise) | generic-Ozsoy only | 0.208 |
| v3 (11 rel types, clean) | generic-Ozsoy only | **0.483** (job 1061277) |
| v3 | + Phase 7.4 in-domain SFT | 0.725 (recorded) |
| v3 | none (no adapter at all) | **0.000** (job 1061290) |

**Both factors are real, and roughly comparably sized.** The schema redesign alone — holding
training fixed at generic-only — more than doubles coverage (0.208→0.483), purely from removing
v2's accidental near-synonym relationship types. Phase 7.4's in-domain SFT then adds a further,
separate increment on top (0.483→0.725) to close most of the remaining gap. Zero fine-tuning at all
is useless regardless of schema (0.000) — a raw base model never learned to continue this prompt's
completion format. So the honest split is: *some* fine-tuning is necessary (0.000→0.483 is the
biggest single jump), the schema redesign is a real, separable, roughly-half-sized contributor on
top of that, and in-domain SFT closes most of the rest. Neither factor alone explains the full
v2→v3 delta.

---

## Stage 2 — Ambiguity Detector probe (G3, job 1032391, 10-question stratified, base LLM)

The v2 3.4 probe classified **all** items `is_ambiguous=False` with `schema_entropy=entity_entropy=0.00`
on every one — the signal was simply absent. On v3 the entropy signal is **live**:

- **entity** items (Q-061 "Tran", Q-062 "Kim") → correctly `is_ambiguous=True`, `entity_entropy=1.00`,
  because the live v3 graph really does contain two distinct Person nodes per surname (the 7.1
  duplicate-surname seed + 7.3 entity-registry check feeding 3.2/3.3). **2/2 entity correct.**
- base Mistral-7B still under-detects **schema/temporal/intent** (overall 4/10, TP=2 FP=0 FN=6 TN=2):
  their candidate distributions come back peaked (`schema_entropy≈0`), and the non-instruct base
  defers to that flat secondary evidence rather than reasoning from the question text.

This is the diagnostic split the gate was designed to produce: v2 was "signal missing"; v3 is
"signal present, base detector too weak on the flat-signal types." The **instruct/API AD** is the
documented stronger-detector path — **deferred this session (no `ANTHROPIC_API_KEY`)**; it is a
config-only swap (`ad`/`dis` in `config/pipeline.yaml`) whenever a key is available.

**Directionally confirmed by ablation (decisions-log 2026-07-16): detection recall tracks the AD
model, not SL/Cov@5 quality — for detection specifically.** The same 10-question probe was re-run
with the same base (non-instruct) AD, varying only the SL adapter underneath it:

| SL adapter | Cov@5 | Detection (base AD, n=10) |
|---|---|---|
| none | 0.000 | 3/10, TP=1 FP=0 FN=7 TN=2 |
| generic-Ozsoy only | 0.483 | 4/10, TP=2 FP=0 FN=6 TN=2 |
| + 7.4 in-domain SFT (this run) | 0.725 | **4/10, TP=2 FP=0 FN=6 TN=2 — identical** |

Cov@5 0.483 and 0.725 give the same detection result with the same AD at this sample size; even
Cov@5=0.000 is only marginally worse. **Caveat, raised directly by the user and worth taking
seriously:** n=10 (n=8 ambiguous) gives confidence intervals of roughly ±25–30 points — wide enough
that "identical" here means *not distinguishable at this sample size*, not *proven zero effect*.
This result is also scoped to **detection only** — it says nothing about whether a flagged item then
gets *resolved* correctly. The full-scale ablation immediately below closes that gap.

**Full C3 ablation — matched SL+QG training tier, "detected AND resolved" (decisions-log
2026-07-16).** The probe above only exercises the AD in isolation at n=10. A full test of "detected
AND resolved" needs the actual C3 condition (Disambiguator → QG → CyVer → execution → evaluation) at
the benchmark's full 120-item scale, with **SL and QG swapped together** to the same training tier —
matching how the claude-sonnet run uses one model uniformly across every stage. (AD and the
Disambiguator were never fine-tuned in this project, at any tier, in any run — so swapping SL+QG
together already is the complete analogue of "match the whole training tier," not a partial one.)

| SL+QG tier | EX | EA | Ambiguous EA | DSR | Detection F1 | Prec | Rec |
|---|---|---|---|---|---|---|---|
| + Phase 7.4 in-domain SFT (reproduces the canonical C3 run exactly) | 12.5 | 27.5 | 31.2 | 0.0 | 30.6 | 75.0 | 19.2 |
| generic-Ozsoy only | 0.8 | 8.3 | 11.2 | 0.0 | 29.6 | 70.6 | 18.8 |
| no adapter at all | 2.5 | 9.2 | 11.2 | 0.0 | 32.0 | 80.0 | 20.0 |

(jobs 1063902 full-tier reproduction, 1063942 generic-only, 1063943 no-adapter — all on the full
120-item benchmark, 80 ambiguous)

Detection (F1/Prec/Rec) stays flat across all three tiers, now confirmed at full statistical power
rather than n=10 — the probe's finding holds up, and this is the robust result in this table.

**Ignore the DSR column.** At recall 19.2% the detector flags only ~20 of 80 items, so DSR moves in
5-point steps and is a 0-or-1-item statistic. It is 0.0 at every tier here, but that is not
evidence of anything: DSR is not interpretable at this recall and should not be cited in either
direction.

What the table *does* support is that **SL/QG quality is not a spent lever**: EX/EA track the
training tier hard (12.5/27.5 at full SFT vs 0.8/8.3 and 2.5/9.2 at the weak tiers — roughly 3× on
EA and 5× on EX). So the natural over-reading of the probe above — "only the AD model matters" — is
still wrong; it's just wrong on EX/EA, which are measured over all 120 items, rather than on DSR.

(The schema-redesign-alone tier, Cov@5=0.483, is actually the *worst* of the three on EX/EA here —
marginally below no-adapter, and tied with it on ambiguous EA — but these are small absolute counts
(differences of 1–2 items), so don't over-read the ordering between the two weak tiers; the clean,
load-bearing contrast is 7.4-SFT vs. either weaker tier, not one weak tier vs. the other.)

**Does the C3-over-C2 gap (criterion #1) itself survive at weaker tiers? (decisions-log
2026-07-16.)** The ablation above only ran C3. C1 is skipped on structural grounds
(`build_condition1.py` uses no adapter at all — the raw base model, no Schema Linker — so it is
provably invariant to this ablation, not a judgment call). C2 is not: it shares the exact SL+QG
stage C3 varies, so a matching C2-only ablation (`kaya/c2_only_ablation_v3.py`, same three tiers,
jobs 1063900 generic-only / 1063941 no-adapter) answers whether disambiguation's value-add over
schema-grounding alone is a full-SFT-only artefact or holds more generally:

| Tier | C2 EX | C3 EX | C2 EA | C3 EA | C2 Amb-EA | C3 Amb-EA | C3−C2 (Amb-EA) |
|---|---|---|---|---|---|---|---|
| + Phase 7.4 in-domain SFT | 15.8 | 12.5 | 28.3 | 27.5 | 27.5 | 31.2 | **+3.7** |
| generic-Ozsoy only | 1.7 | 0.8 | 9.2 | 8.3 | 11.2 | 11.2 | **+0.0** |
| no adapter at all | 3.3 | 2.5 | 10.0 | 9.2 | 11.2 | 11.2 | **+0.0** |

**The gap exists only where SL+QG are actually trained, and is exactly zero at both untrained
tiers.** At full 7.4 SFT, disambiguation adds +3.7 points of ambiguous AREA over schema-grounding
alone; at generic-only and no-adapter, C2 and C3 land on identical ambiguous AREA — when SL+QG
can't produce a usable interpretation to begin with, adding the Disambiguator on top has nothing to
work with, so it adds nothing. This is the shape the architecture predicts: the Disambiguator routes
*among* candidate interpretations, so it needs some minimum grounding to have anything to route
over. **Caveat: these are small absolute counts** (n=80 ambiguous; a 1.2pp move is 1 item), so treat
this as directionally consistent with that reading rather than as a statistically robust trend in
its own right.

---

## Stage 3 — End-to-end evaluation (G4)

> **Source: job 1065123, `results/metrics_mistral7b_v3_qgprops.json`** (120 items × 3 conditions).
> Two G4 result files exist and differ in exactly one factor — whether the QG is shown the schema's
> Properties list. This one (properties on) is canonical; `metrics_mistral7b_v3.json` (properties
> off) is its ablation arm, reported under "The QG properties defect" below.

### Table 1 — Overall (120 questions; %)

| Metric | C1 baseline | C2 schema-grounded | C3 disambiguation | v2 (all C) |
|---|---|---|---|---|
| **EX** | 5.0 | **15.8** | 12.5 | 0.8 |
| **EA / AREA** | 10.8 | 28.3 | 27.5 | 0.8 |
| KG-Valid % | 62.5 | 74.2 | 71.7 | 10–22 |
| Syntax % | 92.5 | 82.5 | 83.3 | 49–93 |
| Schema % | 87.4 | 100.0 | 100.0 | 68–74 |
| Pass@1 | 5.0 | 15.8 | 11.7 | 0.8 |

### Table 2 — Ambiguity-specific (80 ambiguous; %)

| Metric | C1 | C2 | C3 |
|---|---|---|---|
| **Ambiguous EA** | 10.0 | 27.5 | **31.2** |
| DSR | — | — | 0.0 |
| Detection F1 | — | — | **30.6** |
| Detection Prec | — | — | 75.0 |
| Detection Rec | — | — | 19.2 |
| EA — schema (n=20) | 0.0 | 20.0 | **35.0** |
| EA — entity (n=20) | 0.0 | 20.0 | 20.0 |
| EA — intent (n=20) | 5.0 | 15.0 | 15.0 |
| EA — temporal (n=20) | 35.0 | 55.0 | 55.0 |

### Table 3 — Repair / routing (C2, C3; %)

| Metric | C2 | C3 |
|---|---|---|
| Initial Valid % | 74.2 | 70.8 |
| Post-CyVer Valid % | 74.2 | 71.7 |
| Structural Repair % | 0.0 | 2.9 |
| Semantic Repair % | 0.0 | 0.0 |
| Avg Iterations | 0.25 | 0.31 |

**The load-bearing read:** on the ambiguous subset, **C3 (31.2%) > C2 (27.5%)** on AREA, and the
gain is concentrated exactly where the architecture targets it — **schema-type EA 35% (C3) vs 20%
(C2)**. Ambiguous EA is now **cleanly monotonic C1 < C2 < C3 (10.0 → 27.5 → 31.2)**. This is
criterion #1, and it was flatly untestable at v2's floor (C3=C2=0). The schema-grounding jump
(C1→C2) is large and real (EA 10.8→28.3), and disambiguation adds a further, smaller,
type-appropriate increment on top.

The honest counters: overall EX still dips at C3 (12.5 vs C2 15.8 — ~4 questions, where the AD's
few false-negative/low-recall firings don't recover an answer C2 already had); **DSR is 0.0 and
should not be cited** — detection flags ~20 items, so DSR is a 0-or-1-item statistic; detection
recall (19.2%) is too low for it to be informative either way.
`entity` EA is stuck at 20.0 and is **immovable** — it does not respond to the QG properties fix in
either C2 or C3, and C3 *has* Entity Lookup, so it is gated by neither property naming nor entity
resolution. Its cause is currently **unknown** and is an open question, not a closed one.

### The QG properties defect (ablation, 2026-07-17)

The Query Generator was the **only** LLM stage whose prompt omitted the schema's Properties list
(`generator.py` derived it from `prompt_style`; `schema_linker/linker.py:53` passes
`include_properties=True` on every backend, at training *and* inference). This is a defect, not a
design choice: a stage told it is given "the schema" cannot be given 90% of one. It is baked into
data generation too — `pole_sft_data.py:569` builds SL rows *with* properties, `:571` builds QG rows
*without* — so **14 of the v3 schema's 24 properties appear zero times** in the QG's 1800 POLE SFT
completions (`incident_id`, `vehicle_id`, `case_id`, `date`, `descriptor`, …). The QG therefore had
no source for those names at all: not its prompt, not its weights, and not the SL's committed
pattern (bare topology — 1 of 120 beam rows carries any property literal).

**Cost of the defect** (properties OFF → ON, both via `run_evaluation`, single factor):

| | C1 | C2 | C3 |
|---|---|---|---|
| EX | 3.3 → **5.0** | 10.8 → **15.8** | 9.2 → **12.5** |
| EA | 4.2 → **10.8** | 23.3 → **28.3** | 23.3 → **27.5** |
| KG-Valid | 42.5 → **62.5** | 65.8 → **74.2** | 65.0 → **71.7** |
| ambiguous EA | 2.5 → **10.0** | 25.0 → **27.5** | 27.5 → **31.2** |

A matching **6-cell C2/C3 × {full 7.4 SFT, generic-only, no-adapter}** grid (jobs 1063899/1063900/
1063941/1063902/1063942/1063943) shows the effect is **large on validity and modest on correctness**:
KG-Valid improved in 6/6 cells (**+6.7 to +31.7pp**) and EA in 6/6 (+4.2 to +7.5pp), but EX is flat
at both weak tiers. Properties fix schema *conformance*, not *comprehension* — CyVer-rejected
queries become executable-but-wrong ones. **Detection is identical across all seven runs**
(F1 30.6 / Prec 75.0 / Rec 19.2), the check that the manipulation really was QG-only. Few-shots were
deliberately **not** added (unlike the API-path fix, which changed both at once), so the factor is
attributable to properties alone.

**What this does and does not buy.** It removes a real **fairness confound** — claude-sonnet's QG
always saw the full schema while mistral's never did, so part of the three-column gap was schema
access, not capability. But it does **not** rescue the local column: C2 EA **28.3 vs claude-sonnet
57.5** at near-identical SL quality (EM@1 0.667 vs 0.650) — properties closed ~5 of a ~34pp gap
(~15%). The residual is a capability finding, not a measurement artifact, which is the stronger
claim. **Root cause remains unfixed and out of scope**: `pole_sft_data.py:571` still trains the QG
on a property-free schema, so properties=True is an inference-time partial correction with
train/inference mismatched (empirically net-positive; the complete fix is a QG retrain).

---

## Scorecard against the 7 success criteria (project-overview §9)

| # | Criterion | Target | v2 | v3 | v3 Met? |
|---|---|---|---|---|---|
| 1 | C3 > C2 on ambiguous AREA/EX | C3 higher | C3=C2=0 | **AREA 31.2 > 27.5; schema 35 > 20** | ✅ |
| 2 | Monotonic C3 ≥ C2 ≥ C1 (overall EX) | ordered | all 0.008 tied | ambig-EA now cleanly monotonic (10.0→27.5→31.2); overall EX C3 12.5 < C2 15.8 | ⚠ partial |
| 3 | Detection F1 above baseline, usable recall | high recall | F1 23.3, rec 15.2 | F1 30.6, prec 75.0, **rec 19.2** | ⚠ improved, recall low |
| 4 | Per-type C3 gains (schema/entity/temporal) | measurable | all 0 | schema C3 +15pt; temporal realized at C2; **entity immovable at 20.0** | ⚠ schema gain |
| 5 | **SL Cov@5 ≥ 85%** | ≥ 0.85 | 0.208 | **0.725** | ❌ (3.5×, > 0.60 gate) |
| 6 | Post-SFT entropy AUC > 0.62 | improve | 0.592, flat | **0.689, ablations non-flat** | ✅ |
| 7 | High KG-valid + repair recovers invalid | high | 10–22% valid, ~0–1% repair | 62–74% valid, 0–3% repair | ⚠ valid much improved; repair ~nil |

**v2 scored 0/7. v3 meets #1 and #6 outright, materially improves every other criterion, and
misses #5's 0.85 bar while tripling coverage.** Pipeline code is unchanged between v2 and v3, so
none of this delta is a pipeline edit — and it is not attributable to "the substrate" as a single
variable either: the attribution ablation above splits it into a real schema-redesign effect
(0.208→0.483 Cov@5, holding training fixed) and a real Phase-7.4-SFT effect (0.483→0.725) of roughly
comparable size. The precise form of the thesis's methodological point: **the pipeline architecture
was never the bottleneck; the schema-linking substrate was, and that substrate has (at least) two
separable levers, both real.**

---

## What this means (honest read)

1. **The substrate was the bottleneck, and fixing it unblocks the architecture — via two separable
   levers, not one.** Every v2 failure traced to Cov@5 0.208; lifting it to 0.725 flows straight
   through to EA 0.283 and, crucially, to a *demonstrable* C3-over-C2 effect on the ambiguous
   subset. The architecture claim is no longer gated. The attribution ablation shows this Cov@5
   lift is roughly half schema redesign, half in-domain SFT — both real, neither sufficient alone.

2. **The detection ceiling is the detector, not the linker.** Cov@5 0.725 means the right
   interpretation is in the beams 72% of the time, but detection recall is 19% — the base 7B AD
   leaves ambiguity on the table, and this holds regardless of Cov@5 (flat across every tier at
   full 120-item power: F1 29.6/30.6/32.0). The documented, config-only fix is the instruct/API
   `ad`/`dis` backend (executed in Phase 8 — see `results-walkthrough-v3-claude-sonnet.md`).

   Detection being flat does **not** mean SL/QG quality is spent: EX/EA track the training tier
   hard (Stage 2). That distinction rests on EX/EA, not on DSR — **DSR is uninterpretable at recall
   19.2%** (~20 items flagged → 5-point steps → a 1-item statistic) and is not cited here.

3. **Type structure is partly as designed, with one genuine open question.** temporal and schema
   (the types the v3 schema + 7.4 connector register target) carry the gains, and intent is the
   acknowledged hard case — it finally moved (5→15) under the QG properties fix. But **entity is
   immovable at 20.0**, and we do not know why. It does not respond to the QG properties fix in
   either C2 or C3, and C3 — which *has* Entity Lookup — scores identically to C2. So it is gated
   by neither property naming nor entity resolution, and the two obvious explanations are both
   ruled out by measurement. **This is an open question and the clearest target for the next
   investigation** — resist filling it with a third guess.

---

## Run provenance

| Artefact | Source |
|---|---|
| **`results/tables_mistral7b_v3_qgprops.md`, `results/metrics_mistral7b_v3_qgprops.json` — CANONICAL** (QG properties fix; C1+C2+C3) | G4 job 1065123 (2026-07-17, 2h53m, clean), `config/pipeline_v3_qgprops.yaml` via `kaya/93` |
| `results/tables_mistral7b_v3.md`, `results/metrics_mistral7b_v3.json` — **superseded** (properties-off; retained as the ablation's OFF arm) | G4 job 1032398 (2026-07-12, ~3h24m, clean) |
| `results/g1_sl_coverage_mistral7b_v3.json` (Cov@5 0.683/EM@1 0.667 @ dp=0.2) | G1 job 1032328 |
| `results/g1_sl_coverage_mistral7b_v3_locked.json` (Cov@5 0.725/EM@1 0.667 @ dp=1.0) | offline rescore of G2b cache |
| `results/diversity_penalty_sweep_mistral7b_v3.json`, `config/schema_linker_inference.yaml` (dp=1.0) | G2a job 1032339 |
| `results/entropy_probe_mistral7b_v3.json`, `results/beams_mistral7b_v3.jsonl` | G2b job 1032344 (dp=1.0) |
| AD probe (entity_entropy 1.00 live; 4/10 base) | G3 job 1032391 |
| Substrate validation (8/8 gates) | G0 job 1032327 |
| Cov@5 attribution ablation (schema vs. Phase 7.4 SFT: 0.208/0.483/0.725/0.000) | jobs 1061277 (generic-only), 1061290 (no-adapter) |
| AD-probe ablation (detection flat across SL quality, same base AD) | jobs 1061545 (generic-only), 1061546 (no-adapter) |
| Full C3 SL+QG matched-tier ablation (DSR/EX/EA across training tiers) | jobs 1063902 (full-tier reproduction), 1063942 (generic-only), 1063943 (no-adapter) |
| Full C2 SL+QG matched-tier ablation (does C3-over-C2 survive weaker tiers?) | jobs 1063899 (full 7.4), 1063900 (generic-only), 1063941 (no-adapter) |
| Same ablations on the properties-off QG (superseded arm; retained as the properties ablation's OFF cells) | C3: 1061589 / 1062145 / 1061590 · C2: 1062660 / 1062661 |
| **QG properties ablation, 6-cell C2/C3 × 3 tiers** (validity ↑ 6/6, EA ↑ 6/6, detection unchanged 7/7) | C2: 1063899 (full 7.4), 1063900 (generic-only), 1063941 (no-adapter); C3: 1063902 (full 7.4), 1063942 (generic-only), 1063943 (no-adapter) |
