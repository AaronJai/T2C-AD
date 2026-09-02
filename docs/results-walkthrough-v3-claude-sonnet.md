# T2C-AD Results Walkthrough — v3 Substrate, Claude Sonnet 4.6 backend (Phase 8.3)

*Author: Aaron Tan · v3 API E2E: job 1061343 (2026-07-16, ~1h, clean) · Model:
`claude-sonnet` (= `claude-sonnet-4-6`), one API model running the WHOLE pipeline (SL by
temperature sampling, no adapters/GPU) · Companions: the frozen v2-mistral baseline (job 957276,
[`results-walkthrough.md`](results-walkthrough.md)) and the v3-mistral run (job 1065123,
[`results-walkthrough-v3.md`](results-walkthrough-v3.md)).*

This is the third column of the dissertation's comparison. It runs **the same instrumented pipeline
code** on **the same validated v3 substrate** as v3-mistral, changing only the **model**: a strong
instruct API model instead of the fine-tuned Mistral-7B. Read together, the three columns isolate
three axes:

- **v2-mistral → v3-mistral** — *substrate*, which
  [`results-walkthrough-v3.md`](results-walkthrough-v3.md) splits further: the schema redesign and
  Phase 7.4's in-domain SFT are two separable, both-real contributors, so this axis is not a single
  variable.
- **v3-mistral → v3-claude-sonnet** — *model capability* (fine-tuned 7B → strong instruct API).

**Method caveat (locked 5.5 / 2026-06-30).** For an API model, C2/C3 are **stage-presence, not
SFT**: the Schema Linker and Query Generator are *prompted*, not fine-tuned to the gold output
contract. SL distribution = temperature sampling with frequency-weighted (not logprob) scores.
Sampling is nondeterministic, so the cached sample files (`results/beams_claude-sonnet_v3.jsonl`)
ARE the frozen evidence — every downstream rescore is deterministic from the cache; a re-run
regenerates rather than reproduces.

**How the API path is prompted.** Each LLM stage carries a backend-conditional instruct prompt
alongside the local model's completion prompt, selected by a `prompt_style` switch (`"completion"`
is the default and stays byte-identical for the fine-tuned Mistral, protecting its train/inference
prompt match). For the Query Generator that means `QG_SYSTEM_API` — an explicit output contract
(never return whole nodes, `RETURN DISTINCT` for duplicate-prone questions, never invent a property
name outside the schema's Properties list) — plus `include_properties=True` and `_QG_FEW_SHOT_API`,
four examples reused **verbatim** from `data/pole_qg_train.jsonl`, Phase 7.4's own training data, so
the API model learns the target shape from the same curriculum the fine-tuned model trained on.
`build_condition1` (the zero-shot C1 baseline) is deliberately left untouched, keeping its format
comparable to the published Ozsoy checkpoint results. Rationale and history: decisions-log
2026-07-14 (SL) and 2026-07-16 (QG).

---

## The narrative in one line

Swapping the fine-tuned 7B for a strong instruct API model **solves the detector** — lifting
**Detection F1 30.6 → 73.9 and recall 19.2 → 66.2** — and **turns that detection into real
execution accuracy**: **EX is monotonically ordered 7.5 / 37.5 / 52.5 (C1/C2/C3)**, with
**ambiguous EA C3 (57.5) clearly above C2 (50.0)** and **DSR 49.2%**. Given the actual property
names and four worked examples of the target shape, an un-fine-tuned model hits the output contract
that SFT gives the local model for free — so stage-presence is not, on this evidence, a structural
ceiling on execution accuracy.

---

## The gated runbook (8.3 G0–G4, cheapest-first)

Each gate was a go/no-go; none was skipped past a failure. **Total spend ≈ $55–90**, uncosted from
the console.

| Gate | What | Job | Result | Verdict |
|---|---|---|---|---|
| **G0** | Offline suite + benchmark validation on live v3 graph | 1055742 | 323 tests pass; all 8 gates green | ✅ |
| **G0.5** | Raw-output API smoke (egress + parse eyeball) | 1055747→1055754 | egress OK; **caught + fixed a live-API backend bug** for ~$0.10; SL/AD/Dis/QG parse clean | ✅ |
| **G1** | SL intrinsic Cov@5/EM@1, all 120 q, pre-sweep T=0.7 | 1055760 | **Cov@5 0.658 / EM@1 0.650** | ✅ ≥0.60 |
| **G2a** | Temperature sweep (re-lock decoding) | 1055791 | T **0.3** chosen (Cov@5 0.667; fallback — none cleared 0.85) | ✅ (fallback) |
| **G2b** | Entropy probe at locked T | 1055791 | headline AUC **0.525 < 0.62** | ❌ crit #6 |
| **G3** | AD stratified probe — **API SL + API AD** | 1055843 | **10/10 correct, TP=8 FP=0 FN=0 TN=2** | ✅ |
| **G4** | Full 120×3 end-to-end | 1061343 | Tables 1–3 below (clean, 0 tracebacks) | ✅ |

**G0.5 earned its place.** The raw-output smoke crashed on the very first SL call with a live
`400 invalid_request_error: "system: Input should be a valid array"` (the 8.2 Anthropic backend sent
`system=None` on user-only prompts). Fixed in `pipeline/llm/anthropic.py` (omit `system` when empty,
never send null) + regression test. See decisions-log 2026-07-14. A second raw-output smoke
(job 1061322) later validated the API QG prompt on a single question for ~$0.10 before committing to
a full G4 — the cheap-first discipline paying out twice.

**Illustrative G0.5 output (job 1061322, Q-041)** — the API QG's committed query:

```
MATCH (p:Person)-[r]->(i:Incident)-[:OCCURRED_AT]->(l:Location {suburb:'Northbridge'})
RETURN DISTINCT p.name
```

The model reasons that "Northbridge" is the incident's *location* and filters on the real `suburb`
property, and returns the gold's tight `RETURN DISTINCT p.name` projection rather than whole nodes.

---

## Stage 1 — Schema Linker coverage (G1, G2)

**Intrinsic Cov@5 / EM@1 (G1, job 1055760, pre-sweep T=0.7):**

| type | n | Cov@5 | EM@1 |
|---|---|---|---|
| schema | 20 | 0.250 | 0.200 |
| entity | 20 | 0.450 | 0.450 |
| intent | 20 | 0.650 | 0.650 |
| temporal | 20 | 1.000 | 1.000 |
| null | 40 | 0.800 | 0.800 |
| **overall** | **120** | **0.658** | **0.650** |

Cov@5 0.658 clears the ≥0.60 gate and sits beside v3-mistral's 0.683 — comparable coverage from a
prompted instruct model with **zero SFT**. Temporal is solved (1.00); the drag is **schema (0.25)**,
a *measurement* artefact — the model packs all four Person→Incident role edges into one
comma-separated completion, which the intrinsic single-edge `covered()` guardrail scores a miss even
though all four edges are present as candidates downstream (confirmed at G0.5 and G3).

**Temperature sweep (G2a) / entropy probe (G2b, criterion #6 NOT met)** — see decisions-log
2026-07-14 for the full sweep table and the honest read (an instruct
model at low temperature samples near-deterministically, so the secondary entropy signal stays flat
at 0.525 — the flip side of the model's strong direct reasoning, and consistent with the
LLM-primary/entropy-secondary design, project-overview §7).

**Cross-reference (decisions-log 2026-07-16):** a separate ablation established that v2→v3's own
Cov@5 jump (0.208→0.725, on the *mistral* backend) is a genuine two-factor result — the schema
redesign alone (holding training at generic-only) already lifts Cov@5 to 0.483, and Phase 7.4's
in-domain SFT adds the rest. Full table and discussion in
[`results-walkthrough-v3.md`](results-walkthrough-v3.md).

---

## Stage 2 — Ambiguity Detector probe (G3, job 1055843, API SL + API AD)

- **Binary detection: 10/10 correct. TP=8 FP=0 FN=0 TN=2 → recall 1.00, precision 1.00.**
- Detection is carried by **LLM reasoning, not entropy**: most items show `schema_entropy =
  entity_entropy = 0.00`, yet the AD correctly flags ambiguity with a precise rationale.

**Strengthened by a follow-up ablation (decisions-log 2026-07-16).** To check whether detection
recall depends on SL/Cov@5 quality or on the AD model's own reasoning capability, the same 10-question
G3-style probe was re-run with the **same base (non-instruct) AD**, varying only the SL adapter:

| SL adapter | Cov@5 | Detection (base AD, n=10) |
|---|---|---|
| none | 0.000 | 3/10, TP=1 FP=0 FN=7 TN=2 |
| generic-Ozsoy only | 0.483 | 4/10, TP=2 FP=0 FN=6 TN=2 |
| + 7.4 in-domain SFT (recorded v3-mistral G3) | 0.725 | 4/10, TP=2 FP=0 FN=6 TN=2 |

The generic-only and full-SFT rows are **identical**. With the same base AD, detection recall barely
moves across a huge Cov@5 range, and even at Cov@5=0.000 it's only marginally worse. This directly
confirms — with SL quality now the controlled variable, rather than inferred from the AD backend
alone — that **detection recall is gated by which model reasons over the evidence, not by
schema-linker coverage.** Swapping the AD to a capable instruct model (this column) is what actually
moves it, from recall 19–25% to 66.2%. (Caveat: these are n=10 stratified-sample reads, same
methodology as the original G3 gates, never the source of the recorded headline
Detection F1/recall — treat as directional confirmation, not a precise percentage.)

Contrast: v2 was "signal missing", v3-mistral/the ablation points are "signal present, detector too
weak (base model)", and v3-claude-sonnet is "**detector strong enough**."

---

## Stage 3 — End-to-end evaluation (G4, job 1061343, 120×3, clean)

> **Denominator note.** `format_metric_tables` (4.2) prints hardcoded v2 header counts ("(120)"
> here is correct, but the per-type "(n=20)" and the ambiguous "(80)" are right for v3; the known
> 4.2 cosmetic bug — flagged at 7.5 — affects only parenthetical labels, not the values).

### Table 1 — Overall (120 questions; %)

| Metric | C1 | C2 | C3 |
|---|---|---|---|
| **EX** | 7.5 | 37.5 | **52.5** |
| **EA / AREA** | 7.5 | 57.5 | **62.5** |
| KG-Valid % | 87.5 | 96.7 | 97.5 |
| Syntax % | 100.0 | 96.7 | 97.5 |
| Schema % | 100.0 | 100.0 | 100.0 |
| Pass@1 | 2.5 | 37.5 | 50.8 |

### Table 2 — Ambiguity-specific (80 ambiguous; %)

| Metric | C1 | C2 | C3 |
|---|---|---|---|
| **Ambiguous EA** | 3.8 | 50.0 | **57.5** |
| DSR | — | — | **49.2** |
| **Detection F1** | — | — | **73.9** |
| Detection Prec | — | — | 83.6 |
| **Detection Rec** | — | — | **66.2** |
| EA — schema (n=20) | 0.0 | 60.0 | 65.0 |
| EA — entity (n=20) | 5.0 | 30.0 | 40.0 |
| EA — intent (n=20) | 5.0 | 30.0 | 35.0 |
| EA — temporal (n=20) | 5.0 | 80.0 | 90.0 |

### Table 3 — Repair / routing (C2, C3; %)

| Metric | C2 | C3 |
|---|---|---|
| Initial Valid % | 96.7 | 96.7 |
| Post-CyVer Valid % | 96.7 | 97.5 |
| Structural Repair % | 0.0 | 25.0 |
| Semantic Repair % | 0.0 | 4.4 |
| Avg Iterations | 0.00 | 0.02 |

**The load-bearing read — detection AND execution accuracy both solved.**

1. **Detection is the win (criterion #3).** F1 73.9 (prec 83.6, rec 66.2) is 2.4× v3-mistral's 30.6.
   The pipeline's premise — that ambiguity can be detected from schema context — is demonstrated by
   a capable detector, and the AD-probe ablation above confirms this isn't an artefact of SL quality.

2. **EX/EA clears the floor decisively, and the reason is legible from Table 3.** Initial Valid sits
   at 96.7% for both C2 and C3 — the QG's *first* draft is almost always schema-correct, because it
   is shown the real property names and worked examples of the expected shape. **The low repair
   rates are a consequence of that, not a weakness of the repair loop**: with initial validity
   near-saturated there is very little left to repair, so the remaining repair events are a handful
   of items and inherently noisy in percentage terms.

3. **Monotonic ordering and the architecture claim both hold cleanly.** EX 7.5 < 37.5 < 52.5 and
   EA 7.5 < 57.5 < 62.5 (criterion #2). Ambiguous EA C3 (57.5) > C2 (50.0) by 7.5 points on real
   n=80 statistical weight (criterion #1). This is **directly comparable to v3-mistral's own
   architecture-claim demonstration** (AREA 31.2 > 27.5), on a completely different backend.

4. **Per-type gains are broad and type-structure-consistent.** Temporal is strongest (80→90,
   criterion #4's clearest hit); schema and entity show real C3-over-C2 gains (60→65, 30→40); intent
   remains the hardest type (30→35), exactly as the architecture's own design expects.

---

## Scorecard against the 7 success criteria (project-overview §9) — three columns

| # | Criterion | Target | v2-mistral | v3-mistral | **v3-claude-sonnet** |
|---|---|---|---|---|---|
| 1 | C3 > C2 on ambiguous AREA/EX | C3 higher | C3=C2=0 ❌ | AREA 31.2 > 27.5; schema 35 > 20 ✅ | **ambig-EA 57.5 > 50.0 ✅** |
| 2 | Monotonic C3 ≥ C2 ≥ C1 (overall EX) | ordered | all tied at 0.008 ❌ | ambig-EA monotonic; EX C3<C2 ⚠ | **EX 7.5 < 37.5 < 52.5 ✅** |
| 3 | **Detection F1 above baseline, usable recall** | high recall | F1 23.3, rec 15.2 ⚠ | F1 30.6, rec 19.2 ⚠ | **F1 73.9, prec 83.6, rec 66.2 ✅** |
| 4 | Per-type C3 gains (schema/entity/temporal) | measurable | all 0 ❌ | schema +15pt; entity immovable at 20.0 ⚠ | **schema +5, entity +10, temporal +10 ✅** |
| 5 | SL Cov@5 ≥ 85% | ≥ 0.85 | 0.208 ❌ | 0.725 ❌ (3.5×) | 0.658 ❌ (clears 0.60 gate) |
| 6 | Post-SFT entropy AUC > 0.62 | improve | 0.592 flat ❌ | **0.689, non-flat ✅** | 0.525 flat ❌ (LLM-primary by design) |
| 7 | **High KG-valid + repair recovers invalid** | high | 10–22% valid ⚠ | 62–74% valid, 0–3% repair ⚠ | **87–98% valid ✅; repair low (0–25%) because so little needs it ⚠** |

**Reading the three columns as one argument.** claude-sonnet now meets **#1, #2, #3, #4** outright —
more criteria than either mistral column — and its remaining misses (#5, #6) are both *by design*
consequences of stage-presence (no SFT to push Cov@5 past 0.85, no need to hedge across samples so
entropy stays flat), not defects. Put together: the substrate had to be fixed first (v3), the
architecture's *detection* premise needed a capable model (claude-sonnet), and turning detection into
*execution accuracy* needed the output contract that SFT gives fine-tuned models "for free" and that,
for an API model, comes from a small, cheap prompt (properties + four few-shot examples) rather
than the full fine-tuning path.

---

## What this means (honest read)

1. **Detection was the documented next lever from 7.5, and it moved decisively — confirmed
   directly, not just inferred.** The AD-probe ablation (same base AD, varying SL adapter) shows
   detection recall is flat across Cov@5 0.0→0.725; the actual lever is AD-model capability, and
   swapping to an instruct model lifts recall to 66.2%.

2. **Stage-presence is not a structural ceiling on execution accuracy.** An un-fine-tuned model
   *can* hit the gold output contract, given (a) the actual property names in its prompt and (b) a
   few worked examples of the target shape — both cheap. The useful lesson is narrower than "API
   models aren't fine-tuned, so EX stays low": what matters is whether the QG prompt is specified as
   fully as the other three stages', not whether prompting can substitute for SFT in principle. Here
   it can.

3. **Type structure is exactly as designed.** Temporal is the strongest signal throughout (validity,
   detection, EA); schema and entity show real, measurable C3-over-C2 gains; intent is the
   acknowledged hard case across every column of this dissertation. Nothing here is anomalous.

---

## Run provenance

| Artefact | Source |
|---|---|
| **`results/tables_claude-sonnet_v3.md`, `results/metrics_claude-sonnet_v3.json` — CANONICAL** | G4 job 1061343 (2026-07-16, ~1h, clean) |
| `results/tables_claude-sonnet_v3_pre-qgfix.{md,json}` — **superseded** (ran before the API QG prompt existed; retained for the record) | G4 job 1055879 (2026-07-14) |
| `results/api_smoke_claude-sonnet_v3-qgfix.txt` | G0.5 re-verification, job 1061322 (Q-041, API QG prompt) |
| `results/api_smoke_claude-sonnet_v3.txt` | Original G0.5, job 1055754 (post `system=null` fix) |
| `results/g1_sl_coverage_claude-sonnet_v3.json`, `results/beams_claude-sonnet_v3.jsonl` | G1 job 1055760 (frozen sample evidence) |
| `results/diversity_penalty_sweep_claude-sonnet_v3.json`, `config/schema_linker_inference.yaml` (T=0.3) | G2a job 1055791 |
| `results/entropy_probe_claude-sonnet_v3.json` | G2b job 1055791 (CPU rescore of G1 cache) |
| AD probe (10/10, rec 1.00, API SL+AD) | G3 job 1055843 |
| AD-probe ablation (base AD, varying SL adapter) | jobs 1061545 (generic-only), 1061546 (no-adapter) |
| Cov@5 attribution ablation (schema vs. Phase 7.4 SFT) | jobs 1061277 (generic-only), 1061290 (no-adapter) — see `results-walkthrough-v3.md` |
| Substrate validation (8/8 gates) | G0 job 1055742 |
| Backend fix (`system` null → omitted) | decisions-log 2026-07-14; `pipeline/llm/anthropic.py` |
| API QG prompt — output contract + properties + four few-shots (rationale & history) | decisions-log 2026-07-16; `pipeline/query_generator/{prompts,generator}.py` |
| Property-hallucination counts + Q-041 paired example (evidence motivating the API QG prompt) | `results/property_hallucination_claude-sonnet_v3.txt` |
