# T2C-AD Results Walkthrough — Qwen2.5-72B (SFT), v3 + external POLE (Phase 11.4)

*Author: Aaron Tan · G4 runs: job **1148937** (v3, 120×3, 2h23m53s) and job **1148938**
(external POLE, 100×3, 1h50m26s), both 2026-08-31 on Kaya's `rrifcs` H100 partition (node k172,
4× H100 NVL each), both `COMPLETED 0:0` with **0 tracebacks**. Model: `qwen2.5-72b`
(`Qwen/Qwen2.5-72B` **base**, 4-bit/fp16) + the Phase 11.3 two-stage LoRA adapters. Companions:
[`results-walkthrough.md`](results-walkthrough.md) (v2-mistral),
[`results-walkthrough-v3.md`](results-walkthrough-v3.md) (v3-mistral),
[`results-walkthrough-v3-claude-sonnet.md`](results-walkthrough-v3-claude-sonnet.md) (v3-claude),
[`results-walkthrough-qwen-32b.md`](results-walkthrough-qwen-32b.md) (qwen-32B).*

This page adds the **third point on the model-scale axis** — 7B → 32B → 72B on a recipe frozen
since 10.6 — so the axis can be reported as a measured trend rather than a two-point line. It
exists to answer the question 10.7 raised: 10.7 found the *adapter* axis dominates the *scale*
axis (7B→32B = +2.5 pp Cov@5; generic→in-domain = +22 pp). **Does a further 2.2× in parameters
change that? No — and the way it fails to is more interesting than a flat line.**

**All prior artefacts are byte-unchanged** — 95 of the 99 `results/` + `docs/` files checksummed
at session start, including every mistral v2/v3/external, claude v3/external and qwen-32B
v3/external artefact and all four walkthroughs above. The 4 that moved are 11.3's *own* 72B G1
files, deliberately re-measured at the re-locked decoding (below); their dp=1.0 originals are
preserved under `results/_superseded/*_DP1.0_11p3_job1148276-7.*`.

---

## The narrative in one line

Scaling the open model 2.2× **does not move schema linking** (Cov@5 0.750 → 0.733 on v3,
0.780 → 0.770 on external) and **costs detection quality** (v3 F1 60.5 → 41.7), yet the
*architectural* claim survives intact on both substrates — and the one criterion that had never
been met, the entropy signal, is met here **not by scale but by re-tuning beam diversity**. The
dissertation's thesis that this is an architecture story, not a model-size story, is now
supported by three scale points instead of two.

---

## The gated runbook (11.4 G0–G4, cheapest-first)

No gate was skipped past a failure and **no G1 loop back to 11.3 was needed**. G3→G4 were chained
`--dependency=afterok`, so the chain could not advance past a non-zero exit.

| Gate | What | Job(s) | Result | Verdict |
|---|---|---|---|---|
| **G0** | Offline suite + the three properties layers + config key-set diff | — | 451 passed / 5 pre-existing unrelated fails; both configs key-set-identical to their canonical local counterparts bar `active_model`/`results_tag`; guard **demonstrated to fail** with the key removed | ✅ |
| **G1** | Full-benchmark SL Cov@5 / EM@1 at the locked dp | 1148537, 1148540 | v3 **0.733** / 0.683 · external **0.770** / 0.710 (bar ≥ 0.60) | ✅ |
| **Attr.** | Three-way adapter attribution | 1148538/39, 1148541/42 | v3 0.200→0.583→0.733 · ext 0.160→0.400→0.770 | ✅ |
| **G2a** | Diversity-penalty sweep (v3) | 1148406 | dp ∈ {0.2, 0.5, 1.0} → **re-locked dp = 0.5**; hallucination 0.000 at every penalty | ✅ |
| **G2b** | Entropy probe (v3) | 1148896 | AUC **0.643** — **clears** the 0.62 bar | ✅ |
| **G3** | AD stratified probe | 1148935, 1148936 | v3 **6/10** · external **9/10**; AD JSON parses natively | ✅ ran |
| **—** | *Pre-G4 device probe (not a spec gate)* | 1148895, 1148924 | 3 GPUs → OOM; 4 GPUs → fits at 66.5/69.2/69.1 GiB | ✅ |
| **G4** | Full e2e | 1148937, 1148938 | 120×3 and 100×3, 0 tracebacks, 8 artefacts | ✅ |

**Scope notes, recorded rather than glossed.** The G2 sweep and entropy probe run on **v3 only** —
`diversity_penalty_sweep.py` and `entropy_probe.py` both take `--dataset_version v2|v3` with no
`pole_external` branch, so the external substrate reuses the v3-locked penalty as a documented
pragmatic default (the same deferral 10.4 and 10.7 recorded). G3's counts are recorded, not a
numeric gate, per the 7.5/10.4/10.7 convention.

---

## The one number that changed everything: dp = 0.5

**This is the first model in the project whose sweep moved the diversity penalty off 1.0.**

| dp | entropy AUC | Cov@5 | hallucination |
|---|---|---|---|
| 0.2 | 0.630 | 0.725 | 0.000 |
| **0.5** | **0.643** | **0.733** | 0.000 |
| 1.0 | 0.556 | 0.733 | 0.000 |

No penalty cleared the 0.85 Cov guardrail, so the fallback rule picked best (Cov@5, AUC) — a Cov
tie at 0.733 broken by AUC. Everything downstream (G1, all four attribution tiers, G2b, both G4s)
was then run *at* dp=0.5, so the three-way comparison stays single-factor on the adapter.

**Why it matters:** at dp=1.0 this model's entropy AUC is **0.556 — worse than 10.7's 32B 0.570**.
At dp=0.5 it is **0.643**, the first column in the project to clear success criterion #6's 0.62
bar. So criterion #6 is met, and **scale is not what met it**. That is direct evidence for what
project-overview §7 actually claims — *beam diversity at generation time is the bottleneck, not
the scoring function* — since re-tuning the diversity knob moved a signal that 4.6× and 2.2×
parameter scaling had both failed to move. Ablations stayed flat (spread 0.005 ≤ 0.01),
reconfirming that the simplest scorer is sufficient.

---

## Stage 1 — Schema Linker: the adapter axis dominates, at every scale

Three-way attribution, all at dp=0.5 so the adapter is the only factor:

| tier | v3 Cov@5 | external Cov@5 |
|---|---|---|
| no adapter (raw base) | 0.200 | 0.160 |
| + generic Ozsoy | 0.583 | 0.400 |
| **+ generic + POLE (in-domain)** | **0.733** | **0.770** |

Beside 10.7's 32B (v3 0.033 → 0.533 → 0.750; external 0.010 → 0.540 → 0.780), two things stand out.

**Scale buys a better *base*, and in-domain SFT washes the advantage out.** The 72B's no-adapter
tier is 6× the 32B's on v3 (0.200 vs 0.033) and 16× on external (0.160 vs 0.010) — a real
zero-shot schema-linking ability the 32B essentially lacked. By the in-domain tier that advantage
is gone: 0.733 vs 0.750 and 0.770 vs 0.780, i.e. **slightly negative**. The adapter is doing the
work, and it does not need the bigger base to do it.

**The `schema`-type cell reproduces the 10.7 headline.** Cov@5 on the designed-ambiguity edges:
v3 **0.05 → 0.15 → 1.00**, external **0.00 → 0.30 → 0.80**. The generic Ozsoy adapter contributes
almost nothing on the Person→Incident role split; in-domain SFT supplies it entirely. Third
model, same finding.

### The full scale axis

| | 7B (SFT) | 32B (SFT) | 72B (SFT) |
|---|---|---|---|
| v3 Cov@5 | 0.725 | 0.750 | **0.733** |
| external Cov@5 | 0.810 | 0.780 | **0.770** |
| v3 EM@1 | 0.667 | 0.683 | **0.683** |
| external EM@1 | 0.620 | 0.660 | **0.710** |

Cov@5 is flat-to-declining across a 10× parameter range while EM@1 rises monotonically on
external (0.620 → 0.660 → 0.710). The Cov@5−EM@1 gap on external collapses 0.190 → 0.120 →
**0.060**: the bigger model's top-1 keeps improving while its five beams add less and less. 11.3
flagged this as an observation to test; it holds at the locked decoding. For an architecture that
needs the gold interpretation to be *in the distribution* rather than merely at the argmax, this
is the load-bearing risk of scaling — and it is the same phenomenon dp=0.5 partially counteracts.

---

## Stage 2 — Ambiguity Detector (G3): scale made the detector *more conservative*

| | v3 | external |
|---|---|---|
| **72B** | 6/10 (TP=4 FP=0 FN=4 TN=2) | 9/10 (TP=7 FP=0 FN=1 TN=2) |
| 32B (10.7) | 8/10 (TP=6 FP=0 FN=2 TN=2) | 9/10 (TP=7 FP=0 FN=1 TN=2) |
| 7B (10.4, external) | — | 6/10, all 4 TPs via the entropy fallback |

The 72B emits well-formed AD JSON with substantive rationales — it is **not** falling back to
`entity_entropy`, so 10.7's qualitative finding (the 32B was the first local model whose detector
reasons for itself) extends to this scale. The entropy evidence the two models received on v3 is
**byte-identical** (6 items at schema=0.00/entity=0.00, 4 at schema=0.00/entity=1.00), so the
2-question v3 gap is purely the LLM's own judgement: the 72B flagged exactly the four
entropy-positive items and declined the rest, reasoning e.g. *"the relationship type
(Person)-[:SUSPECTED_OF]->(Incident) has a score of 1.00, indicating no schema ambiguity"* — where
the 32B called two such unanimous-distribution items correctly. **On n=10 stratified that is two
questions and well inside noise; it is reported as an observation, not a finding.** FP=0 on both
substrates for both models, so precision remains untested at this sample size.

The full-benchmark G4 detection numbers tell the same story with more power: **v3 F1 41.7 (P 68.6
/ R 30.0) vs the 32B's 60.5**, external **77.4 (P 88.9 / R 68.6) vs 82.2**. Precision is high and
recall is what falls — the conservatism is real, and on v3 it is large.

---

## Stage 3 — End-to-end (G4)

### v3 substrate — job 1148937, 120×3, 2h23m53s

| Metric | C1 | C2 | C3 |
|---|---|---|---|
| EX | 5.8 | 19.2 | **20.8** |
| EA / AREA | 7.5 | 35.0 | **44.2** |
| Ambiguous EA | 3.8 | 35.0 | **45.0** |
| KG-Valid % | 90.0 | 77.5 | 81.7 |
| Detection F1 | — | — | 41.7 |
| DSR | — | — | 20.0 |
| Structural repair % | — | 15.6 | 26.7 |

**Monotonic C1 < C2 < C3 on both EX and EA**, and ambiguous EA C3 45.0 > C2 35.0 — criteria #1
and #2 met. Per-type EA (C2→C3): **entity 20 → 65**, schema 30 → 30, temporal 60 → 60, intent
30 → 25. The entity cell is the standout of the whole run: +45 pp from detect-then-commit alone,
against the 32B's 20 → 25.

### External POLE substrate — job 1148938, 100×3, 1h50m26s

| Metric | C1 | C2 | C3 |
|---|---|---|---|
| EX | 41.0 | 36.0 | **43.0** |
| EA / AREA | 50.0 | 40.0 | **53.0** |
| Ambiguous EA | 40.0 | 31.2 | **47.5** |
| KG-Valid % | 97.0 | 76.0 | 85.0 |
| Detection F1 | — | — | 77.4 |
| DSR | — | — | 50.0 |
| Structural repair % | — | 14.3 | 31.8 |

Ambiguous EA C3 47.5 > C2 31.2 (+16.3 pp) — criterion #1 met. Per-type EA (C2→C3): **temporal
15 → 60**, schema 20 → 35, intent 20 → 30, entity 70 → 65. The qualitative buckets concentrate
exactly where the architecture targets: `fixed` = {temporal 8, intent 2}, `regressed` = {entity 3}.

**C2 and C1 are indistinguishable on this substrate** (EX 36.0 vs 41.0; EA 40.0 vs 50.0). The
point estimates put C2 below C1, and the same shape appears in the 32B — but **11.5's paired
bootstrap shows every one of those margins spans zero**: overall ΔEX C2−C1 **−5.0 [−13.0, +2.0]**,
overall ΔEA **−10.0 [−20.0, +0.0]**, ambiguous ΔEA **−8.8 [−21.2, +3.8]**, and the 32B's
**−3.0 [−12.0, +6.0]**. At n=100 this benchmark cannot tell the ordering apart from a tie.

*Superseded reading (11.5, 2026-08-31).* This paragraph originally called the gap "a property of
the external substrate + the SFT recipe rather than a one-run artefact" and recorded it as the one
place criterion #2 fails. **That is withdrawn.** Two columns agreeing in sign is not evidence when
neither margin clears zero, and the honest statement is "no measurable C2−C1 effect on external",
not a regression to be explained. The *mechanisms* documented elsewhere in this page — variable
rebinding, the `surname`→`name` substitution, the `beam_k=1` schema-linker aborts — are real and
individually visible in the records; what the intervals deny is that they add up to a net effect
this benchmark can resolve. See [`variance-and-error-bars.md`](variance-and-error-bars.md).

**Does 10.7's strongest cell hold?** Partially. External `temporal` C3 was the project's single
best result at 32B (EA 35 → 100). At 72B it is **15 → 60** — same direction, same mechanism
(8 of the 10 `fixed` items are temporal), roughly half the magnitude, from a much weaker C2 base.

---

## The scale-vs-adapter table (the phase's headline)

| axis | v3 Cov@5 | external Cov@5 | v3 ambiguous EA (C3) | external ambiguous EA (C3) |
|---|---|---|---|---|
| **scale**: 7B → 32B → 72B | 0.725 → 0.750 → 0.733 | 0.810 → 0.780 → 0.770 | 31.2 → 42.5 → 45.0 | 23.8 → 60.0 → 47.5 |
| **adapter** (72B): none → generic → in-domain | 0.200 → 0.583 → 0.733 | 0.160 → 0.400 → 0.770 | — | — |
| **adapter** (32B, 10.7): none → generic → in-domain | 0.033 → 0.533 → 0.750 | 0.010 → 0.540 → 0.780 | — | — |

Across a 10× parameter range the schema linker moves by **±2.5 pp**. Across the adapter axis at a
*fixed* model it moves by **+53 pp (v3)** and **+61 pp (external)**. The adapter axis dominates the
scale axis by more than an order of magnitude, and this is now a three-point measurement.

---

## The malformed-Cypher rate, measured rather than asserted

10.4 and 10.7 attributed the residual EX gap to malformed generation — empty labels `(n:)` and
variable rebinding — as a **capacity** limit (decisions-log 2026-08-23). With three scale points
that is testable. Counting both failure modes mechanically over every `generated_cypher_final` in
every condition of every `qual_records_*` artefact:

| column | n | empty `(n:)` | rebind | either | rate |
|---|---|---|---|---|---|
| mistral-7B, external | 300 | 18 | 25 | 43 | **14.3%** |
| qwen-32B, external | 300 | 0 | 1 | 1 | **0.3%** |
| **qwen-72B, external** | 300 | 0 | 13 | 13 | **4.3%** |
| qwen-32B, v3 | 360 | 3 | 0 | 3 | **0.8%** |
| **qwen-72B, v3** | 360 | 0 | 24 | 24 | **6.7%** |
| claude-sonnet, both | 660 | 0 | 0 | 0 | **0.0%** |

**The capacity story does not survive contact with the measurement.** The trend is *not* monotone
in model size: the 72B is 14× worse than the 32B on external and 8× worse on v3. Two facts
identify the real mechanism:

1. **Empty labels are gone** (18 → 0 → 0). That failure mode *was* capacity-linked and scale did fix it.
2. **Every 72B failure is variable rebinding, and it occurs 0 times in C1** — 0/120 and 0/100 in
   baseline, against 13/120 and 11/100 in C2. The *base* 72B never does it; only the fine-tuned
   SL+QG path does, in one stereotyped form: reusing a single variable across both ends of an
   edge, e.g. `MATCH (p:Person {name:'Daniel Kim'})-[:USES_PHONE]->(p:Phone)`.

So the residual is **an artefact of the in-domain SFT, not a capacity limit** — which is why a
2.2× larger model regressed on it. The honest restatement for the dissertation is that 10.4/10.7's
narrative attribution was half right (empty labels) and half wrong (rebinding), and only measuring
across three scale points separated the two. Worth noting the architecture partly self-heals here:
on external, C3's retry path cuts rebinds from 11 to **2** (C2→C3), though on v3 it does not
(13 → 11).

---

## The four-model × two-substrate matrix

### v3 substrate (120 questions, 80 ambiguous; %)

| Metric | mistral-7B (SFT) | claude-sonnet (instruct) | qwen-32B (SFT) | **qwen-72B (SFT)** |
|---|---|---|---|---|
| EX C1/C2/C3 | 5.0 / 15.8 / 12.5 | 4.2 / 39.2 / 54.2 | 5.8 / 20.0 / 25.0 | 5.8 / 19.2 / **20.8** |
| EA C1/C2/C3 | 10.8 / 28.3 / 27.5 | 5.0 / 59.2 / 62.5 | 7.5 / 35.8 / 43.3 | 7.5 / 35.0 / **44.2** |
| Ambiguous EA C3 | 31.2 | 56.2 | 42.5 | **45.0** |
| Detection F1 | 30.6 | 75.7 | 60.5 | **41.7** |
| DSR | 0.0 | 50.0 | 19.6 | **20.0** |
| SL Cov@5 | 0.725 | — | 0.750 | **0.733** |

### External POLE substrate (100 questions, 80 ambiguous; %)

| Metric | mistral-7B (SFT) | claude-sonnet (instruct) | qwen-32B (SFT) | **qwen-72B (SFT)** |
|---|---|---|---|---|
| EX C1/C2/C3 | 14.0 / 21.0 / 24.0 | 20.0 / 59.0 / 64.0 | 40.0 / 37.0 / 53.0 | 41.0 / 36.0 / **43.0** |
| EA C1/C2/C3 | 14.0 / 21.0 / 26.0 | 21.0 / 64.0 / 70.0 | 41.0 / 45.0 / 64.0 | 50.0 / 40.0 / **53.0** |
| Ambiguous EA C3 | 23.8 | 63.7 | 60.0 | **47.5** |
| Detection F1 | 61.2 | 82.0 | 82.2 | **77.4** |
| DSR | 30.4 | 64.4 | 56.1 | **50.0** |
| SL Cov@5 | 0.810 | — | 0.780 | **0.770** |

**The 32B remains the best local column on both substrates.** That is the phase's result, and it
is reported as such: a 2.2× larger base, trained on a byte-identical recipe, does not beat it.

---

## Scorecard against the 7 success criteria (project-overview §9)

| # | Criterion | v3 | external | Note |
|---|---|---|---|---|
| 1 | C3 ambiguous EA > C2 | ✅ 45.0 > 35.0 · CI **+10.0 [+2.5, +17.5]** | ✅ 47.5 > 31.2 · CI **+16.2 [+7.5, +26.2]** | met on both. **11.5:** external clears zero under both strata; v3 clears it on the headline stratum but not abort-excluded (**+6.8 [+0.0, +13.5]**) — v3 is indicative, external is evidential |
| 2 | Monotonic C3 ≥ C2 ≥ C1 | ✅ EX and EA both | ⚠ **not measurable** — C2−C1 EX −5.0 [−13.0, +2.0] spans zero | **11.5 revises this from ❌ to ⚠.** No C2−C1 effect is resolvable on external either way; on v3 the ordering holds on points, though the C3−C2 step (**+1.7 [−2.5, +6.7]**) is itself within noise |
| 3 | Detection works | ⚠ F1 41.7, recall 30.0 | ✅ F1 77.4, recall 68.6 | v3 recall is the weakest of any Qwen column |
| 4 | Per-type gains | ⚠ entity +45, others flat | ✅ temporal +45, schema +15, intent +10 | external hits three of four targeted types |
| 5 | Cov@5 ≥ 0.85 | ❌ 0.733 | ❌ 0.770 | missed by **every** model incl. the API one |
| 6 | Entropy AUC > 0.62 | ✅ **0.643** | — | **first column ever to meet it** — via dp=0.5, not scale |
| 7 | KG-valid + repair | ✅ 81.7%, repair 26.7% | ✅ 85.0%, repair 31.8% | structural repair recovers a real fraction on both |

Meets #1 on both substrates, #2/#6 on v3, #3/#4/#7 on external — and **#6 for the first time in
the project**. Misses #5 everywhere, as every column has. **After 11.5, #2 on external is a
non-result rather than a failure**, and #1's v3 margin is indicative rather than evidential.

---

## What this means (honest read)

**The scale axis is closed, and it is flat.** Three points on a frozen recipe (7B → 32B → 72B)
move schema-linker Cov@5 by ±2.5 pp while the adapter axis moves it by +53/+61 pp at fixed size.
A flat axis at three points is a stronger dissertation claim than a rising one at two, and it is
the claim the architecture argument wants: what matters is what you train on and what stages you
build, not how big the base is.

**Two results actively cut against "bigger is better".** Detection F1 falls on both substrates
(v3 60.5 → 41.7), driven by recall — the larger model reasons well but declines to call ambiguity
when the schema linker's distribution is unanimous. And the malformed-Cypher rate *rises*
(0.3% → 4.3% external, 0.8% → 6.7% v3), traceable to an SFT artefact the base model does not
exhibit. Neither is a defect in the pipeline; both are properties of the model column, and both
are the kind of thing only a third point could reveal.

**The one genuine gain came from a knob, not from parameters.** Criterion #6 had never been met.
It is met here at dp=0.5 — while the *same model* at dp=1.0 scores 0.556, below the 32B. The
secondary Bayesian signal was never capacity-limited; it was diversity-limited, exactly as §7
argued from the start. This is the strongest single piece of evidence in the project for the
LLM-primary / entropy-secondary design decision, and it arrived from the cheapest gate in the chain.

**Caveats kept.** Every per-type cell is n=20 and every AD probe is n=10 stratified with FP=0, so
precision is untested and single-cell moves of 1–3 questions are noise; every column remains n=1
on training seed, which 11.5's dropped part B would have addressed.

**Amended 2026-08-31 after 11.5 (part A).** The paired bootstrap has since measured the sampling
variance this page could only gesture at, and two readings above are revised rather than left
standing: the external C2 < C1 ordering is **withdrawn as a finding** (all its margins span zero —
see the External POLE section), and criterion #1's v3 margin is **downgraded to indicative**
(it clears zero on the headline stratum but not under abort exclusion). The per-type caveat is
now quantified: a 95% CI on an n=20 cell is ~15 pp wide, so no per-type reading on this page
should be defended on a margin below that. Everything else stands. Full intervals:
[`variance-and-error-bars.md`](variance-and-error-bars.md).

---

## Run provenance

| Artefact | Job | Elapsed |
|---|---|---|
| G2a sweep (v3) | 1148406 | 35m39s |
| G1 + attribution ×6 (dp=0.5) | 1148537–1148542 | 12m21s – 59m10s |
| G2b entropy probe | 1148896 | 22s (GPU-free rescore) |
| Device probe, 3 GPU (OOM) / 4 GPU (fits) | 1148895 / 1148924 | 6m23s / 6m36s |
| G3 AD probe v3 / external | 1148935 / 1148936 | 8m12s / 7m43s |
| **G4 v3, 120×3** | **1148937** | **2h23m53s** |
| **G4 external, 100×3** | **1148938** | **1h50m26s** |

All on `rrifcs`/k172. G4s used `--gres=gpu:h100:4` (see decisions-log 2026-08-30 — the spec's
3-card sizing OOMs, because `run_evaluation.main()` keeps C1's and C2's models resident while C3
loads, making the real peak six 41.5 GiB loads, not three). Each G4 ran its own background Neo4j
on an isolated data dir and a per-job Bolt port (:28937 / :28938), and both logged
`G0 runtime assert PASSED: qg_include_properties is True, active_model == 'qwen2.5-72b'` before
any model loaded.
