# Project Overview

> **Read this first, before any implementation step.** It is the authoritative source
> for *what* this project is and *why*. The per-step specs in `feature-specs/` cover
> *how*. If a step's spec contradicts this document on intent, stop and ask.

---

## 1. What This Is

Honours thesis project at the University of Western Australia (UWA), supervised by
Assoc. Prof. Tim French and Assoc. Prof. Wei Liu.

**Research question:** How can ambiguity in natural-language questions be explicitly
detected and resolved *before* Cypher query generation over a knowledge graph?

**Core contribution:** A multi-agent Text-to-Cypher (T2C) pipeline that treats
disambiguation as an explicit architectural stage — distinct from prior work where
schema linking silently commits to a single interpretation without detecting or
recording that a choice was made. The defensible novel claim is not "ambiguity
exists" (prior work acknowledges this) but that **schema linking is the architectural
locus of silent commitment**, and that making ambiguity a named, explicit pipeline
event at that locus is what improves execution accuracy.

---

## 2. Goals

1. Build a model-agnostic T2C pipeline with an explicit ambiguity-detection and
   disambiguation stage between schema linking and query generation.
2. Show that the schema linker can emit a **candidate distribution** (not an argmax)
   and that ambiguity can be detected from schema context alone — without ambiguity
   type labels at inference time.
3. Demonstrate, via a three-condition evaluation, that resolving ambiguity improves
   Cypher execution accuracy over a schema-grounded system that commits silently.

---

## 3. Pipeline Flow

```
NL question
   │
   ▼
Schema Linker ──▶ CandidateMapping            (distribution over schema patterns; never argmax)
   │
   ├─▶ Entity Lookup (live Neo4j) ──▶ EntityLookupResult   (KG instances matching named mentions)
   │
   ▼
Bayesian Scorer ──▶ (schema_entropy, entity_entropy)
   │
   ▼
Ambiguity Detector ──▶ AmbiguityResult        (LLM self-assessment PRIMARY; entropy SECONDARY signal)
   │
   ▼
Disambiguator ──▶ SchemaMapping               (commits ONE interpretation; or top-1 if unambiguous)
   │
   ▼
Query Generator ──▶ Cypher
   │
   ▼
CyVer Validation ──▶ ValidationResult         (Syntax → Schema → Properties; typed error routing)
   │   ├ syntax fail      ─▶ back to Query Generator   (inner loop, ≤2)
   │   ├ schema/props fail ─▶ back to Schema Linker     (outer loop, ≤3)
   │   └ accept
   ▼
DB Executor ──▶ ExecutionResult
   │
   ▼
Semantic Evaluator ──▶ EvaluationResult
       └ wrong_result (Condition 3) ─▶ back to Disambiguator   (disambiguation loop, ≤1)
```

**Three feedback loops:** syntax failure → Query Generator (≤2, no retry-budget cost);
schema/properties failure → Schema Linker (≤3 outer retries); semantic mismatch →
Disambiguator (≤1, Condition 3 only).

---

## 4. Components (one feature-spec per step)

| Stage | Role | Implementation |
|---|---|---|
| Schema Linker | Identify relevant node labels, relationship types, properties. Emit a ranked **candidate distribution** via diverse beam search, not argmax. | Fine-tuned LLM (LoRA on Neo4j Text2Cypher 2025v1) |
| Entity Lookup | Resolve named mentions to real KG node instances via fuzzy match against **live Neo4j** property values. Supplies entity-candidate distribution. | rapidfuzz + neo4j driver |
| Bayesian Scorer | Normalised Shannon entropy over schema candidates and entity candidates. Secondary ambiguity signal. | Pure arithmetic |
| Ambiguity Detector | Classify ambiguous (schema / entity / intent / temporal). LLM self-assessment is primary; entropy scores are injected as evidence, not a hard gate. | Few-shot prompted LLM |
| Disambiguator | Commit one interpretation as a structured `SchemaMapping` (Cypher-syntax). Automated mode built; interactive (EIG-based) mode is a documented stub. | Few-shot prompted LLM |
| Query Generator | Generate Cypher from original question + committed pattern + schema. | Fine-tuned LLM (LoRA on Neo4j Text2Cypher 2025v1) |
| CyVer Validation | Deterministic Syntax → Schema → Properties validation; each failure routes to a different upstream stage. | CyVer (Mandilara et al.) |
| DB Executor | Execute validated Cypher against Neo4j. | neo4j Python driver |
| Semantic Evaluator | Compare results to ground-truth interpretations. Primary: Execution Accuracy. Secondary: relaxed AREA. | Frozenset comparison + sentence-transformers fallback |

All LLM stages type against a common `BaseLLM` interface and are **swappable by config**
between local (HuggingFace + LoRA) and API (OpenAI, Anthropic) backends. Mistral 7B is
the default base model — it is one example, not a hard dependency.

---

## 5. Knowledge Graph

**SyntheticPoliceKG** — synthetic policing KG on a POLE schema (Person, Object, Location,
Event), implemented in Neo4j (local Docker). Definition: `SyntheticPoliceKG.cypher`.

- **9 node labels:** Person, Incident, Case, Location, Vehicle, Phone, Evidence,
  Organisation, Communication.
- **28 relationship types**, including SUSPECTED_OF, WITNESSED, VICTIM_OF, INVESTIGATES
  (the four Person→Incident edges that are the primary source of *schema* ambiguity),
  and temporal edges (LIVES_AT, OWNS, USES_PHONE, WORKS_FOR, ASSOCIATED_WITH) carrying
  `active` / `from_date` / `to_date` (the source of *temporal* ambiguity).
- The schema file defines structure; **actual entity values** (names, addresses,
  identifiers) live in the loaded database — Entity Lookup must query the live DB, not
  the file.

**v3 (Phase 7, decided 2026-07-06).** The first full E2E run (job 957276) localised the
accuracy floor to SL intrinsic coverage (Cov@5 0.208 vs the ≥0.85 criterion), and the
diagnosis attributed part of that to the v2 schema itself: many of the 28 relationship
types are accidental near-synonyms (`RELATES_TO`/`RELATED_TO`/`LINKED_TO`; seven `*_AT`
location edges) — lexical noise that deflates schema linking without testing
disambiguation. **v3** (`SyntheticPoliceKG-v3.cypher`, specs `feature-specs/phase7/`)
shrinks to **6 node labels / 11 relationship types**, keeping only *designed* ambiguity:
the four Person→Incident role edges (schema), duplicate names/aliases in the data
(entity), and dated `LIVES_AT`/`OWNS`/`USES_PHONE`/`ASSOCIATED_WITH` edges (temporal).
v2 stays frozen as the recorded baseline; the v2→v3 before/after on identical pipeline
code is part of the thesis argument.

---

## 6. Evaluation

**Benchmark (v2):** `benchmark-updated.json` — 125 annotated questions, **50 ambiguous /
75 unambiguous**. Canonical for Phases 0–6 and frozen as the baseline: `ambiguity_type ∈
{schema, entity, intent, temporal, null}`, no empty strings, no compound labels. **No
migration or remapping step exists.**

Ambiguity type distribution (v2): schema 13, entity 11, intent 11, temporal 15, null 75.

**Benchmark (v3, Phase 7):** `benchmark-v3.json` — 120 questions, **80 ambiguous /
40 unambiguous** (20 per ambiguity type, so per-type cells are statistically
reportable), same item contract as v2. Gold queries are capped at **3 hops**;
`num_hops` is recorded metadata only (the dissertation reports single- vs multi-hop —
v2's uniform 1–5-hop stratification is dropped as orthogonal to the research question).
v3 ships with an executable validation harness (7.2): every gold query must run
non-empty on the live KG and every ambiguous item's interpretations must return
**pairwise-distinct** result sets — the precondition that makes DSR/EA measurable.
v3 is canonical for all new runs once that harness passes.

**Three experimental conditions:**

| Condition | What it isolates |
|---|---|
| 1 — Baseline | Zero-shot base model, full schema injected, no fine-tuning |
| 2 — Schema-grounded | Effect of Cypher-domain SFT (Schema Linker + Query Generator), no disambiguation |
| 3 — Disambiguation-enhanced | Additional effect of the disambiguation pipeline on top of SFT |

**Primary metric:** Execution Accuracy (EX) against the annotated default interpretation.
**Secondary metric:** relaxed AREA — credits any valid interpretation match, separating
valid-but-non-default failures from wrong-result failures. Because the pipeline commits
to a single interpretation per query, EX is the headline; AREA is a diagnostic.
**Additional:** Pass@1, DSR (Disambiguation Success Rate), Detection F1, per-type EX.

---

## 7. Entropy Probe — Established Finding

A pre-pipeline probe validated whether Shannon entropy over diverse beam-search outputs
from the Schema Linker carries a reliable ambiguity signal. Result: the signal is **weak
but real and direction-correct** at 7B scale (fine-tuned text2cypher model AUC ≈ 0.62 vs
≈ 0.49–0.53 for base models; ablations across entropy/dominance/normalisation are flat,
so the scoring function is not the bottleneck — beam diversity at generation time is).

**Design implication (load-bearing):** **LLM self-assessment is the primary ambiguity
signal; the Bayesian entropy scorer is secondary.** The probe is re-run on the
POLE-specific fine-tuned Schema Linker (step 2.3) to confirm the signal improves; the
`diversity_penalty` is selected during training (step 2.2) by entropy-AUC separation.

---

## 8. Scope

**In scope**
- POLE synthetic KG; the 125-question v2 benchmark (frozen baseline) and the
  120-question v3 benchmark (80 ambiguous) with its concise 6-label/11-relationship
  schema (Phase 7).
- In-domain POLE SFT data for the Schema Linker + Query Generator (Phase 7.4),
  template-generated over the v3 schema and text-disjoint from the benchmark.
- Four ambiguity types: schema, entity, intent, temporal.
- Automated disambiguation as the evaluated modality.
- Three-condition evaluation with the metrics in §6.
- Schema Linker + Query Generator fine-tuning (LoRA) on the Neo4j Text2Cypher 2025v1 dataset (~40K; 35.9K train, 4.44K test).
- Bayesian schema-entropy + entity-entropy as a secondary signal; LLM primary.
- CyVer deterministic validation with typed error routing.
- Model-agnostic backends (local HuggingFace + API).
- A Gradio demo exposing the interactive-disambiguation interface contract (stub).

**Out of scope (limitations / future work)**
- Interactive (EIG-based) disambiguation as an *evaluated* modality — interface stub
  only; theoretical basis is Qiu et al. (EIG).
- Multi-label / compound ambiguity — the four compound questions are collapsed to a
  single dominant type (temporal); multi-label handling is future work.
- Confidently-wrong Schema Linker (all beams agree on a wrong mapping) — undetectable
  by design; the pipeline proceeds silently. Disambiguation targets *detectable*
  ambiguity, not undetectable error.
- The cosine pre-filter is an optional scalability aid, not a contribution; off by default.
- Non-synthetic / real-world KGs.
- Beating state-of-the-art absolute accuracy. At 7B scale the contribution is
  architectural; modest absolute numbers reported honestly are an acceptable result.

---

## 9. Success Criteria *(draft — confirm/adjust)*

The thesis succeeds if the architecture is *demonstrated to work as claimed*, not if it
beats SOTA. The criteria below were first scored on v2 (all ❌ — see
`docs/results-walkthrough.md`, root cause SL Cov@5 0.208), re-scored on the v3 dataset at
Phase 7.5 (`docs/results-walkthrough-v3.md`, fine-tuned Mistral-7B: meets #1 and #6
outright, materially improves the rest), and re-scored again at Phase 8 with an API
instruct model (Claude Sonnet 4.6) running the whole pipeline in place of the fine-tuned
7B (`docs/results-walkthrough-v3-claude-sonnet.md`: meets #1–#4 outright, more criteria
than either Mistral column — misses #5/#6 only as by-design consequences of
stage-presence having no SFT to push past, not defects). Targets are unchanged across
versions. Concretely:

1. **Architectural claim.** On the 50-question ambiguous subset, Condition 3 achieves
   higher AREA (and EX) than Condition 2 — i.e. explicit disambiguation adds measurable
   value beyond silent schema grounding.
2. **Monotonic ordering.** C3 ≥ C2 ≥ C1 on ambiguous-subset EA and overall EX, validating
   that each architectural addition contributes.
3. **Detection works.** Ambiguity Detector binary Detection F1 is meaningfully above a
   stated baseline, with recall high enough that ambiguous questions actually enter the
   disambiguation loop (DSR is uninformative if recall is low).
4. **Per-type signal.** Measurable C3 gains on schema, entity, and temporal (the types the
   architecture targets); intent is acknowledged as the hardest.
5. **Schema Linker carries the answer.** Cov@5 ≥ 85% on the POLE benchmark (gold pattern
   present in the top-5 beams) — the disambiguator can only succeed if the right
   interpretation is in the distribution.
6. **Probe confirmation.** Post-SFT entropy AUC improves over the ≈0.62 general-model
   baseline, confirming the secondary Bayesian signal is usable.
7. **Validity.** High KG-valid rate after CyVer routing; the structural-repair loop
   recovers a non-trivial fraction of initially invalid queries.

---

## 10. Locked Design Decisions

- Schema Linker outputs a **candidate distribution**, not argmax — foundation of the
  disambiguation contribution.
- Disambiguator output is a structured `SchemaMapping` in Cypher syntax (not a rewritten
  NL question). The original question is never modified.
- CyVer schema/properties failure routes back to the **Schema Linker**, not just the
  Query Generator.
- `previously_tried_mappings` persists across disambiguation retries **and** Schema Linker
  outer-loop retries (amended 2026-06-10: the linker decodes deterministically, so an outer
  retry reproduces the same candidate set — persistence is what makes the retry able to commit
  a different interpretation). Retry loops carry CyVer diagnostics back into the Query
  Generator prompt as inference-only `error_feedback`; without it, deterministic decoding
  would reproduce the identical failure on every retry.
- Ambiguity type labels are **post-hoc annotation for evaluation only** — never fed to
  any LLM at inference time.
- Entity ambiguity requires a **live Neo4j connection** — it matches against real node
  property values, not the schema file.
- Custom Python pipeline — **no LangGraph**.
- **v2 artefacts are frozen** (added 2026-07-06): `benchmark-updated.json`,
  `SyntheticPoliceKG.cypher`, and the job-957276 results are the recorded baseline and
  are never edited; Phase 7's v3 dataset is selected purely by config
  (`dataset_version`/`results_tag`), and all v3 artefacts are version-tagged so the two
  never collide.
- **In-domain SFT data must be question-text-disjoint from the benchmark** (7.4's hard
  gate) — the benchmark measures generalisation within the schema, not memorisation.

---

## 11. Tech Stack

Python · `BaseLLM`-abstracted backends (default Mistral 7B, Apache 2.0; OpenAI/Anthropic
via API) · HuggingFace / PEFT / LoRA · Neo4j (local Docker) · CyVer · sentence-transformers
· rapidfuzz · Neo4j Text2Cypher 2025v1 dataset (Ozsoy et al.; ~40K, Apache-2.0) · Gradio (demo).

---

## 12. Key Papers

Ozsoy et al. (Neo4j Text2Cypher 2025v1, ~40K; Gemma fine-tune — training data + baseline) · DTS-SQL
(decomposed fine-tuning — Schema Linker design) · DIN-SQL (schema linking as dominant
failure) · Hornsteiner et al. (modular pipeline — error routing) · Gusarov et al.
(GraphRAG — schema injection format) · Mandilara et al. (CyVer — direct component) ·
AmbiGraph-Eval / Tian et al. (AREA metric, taxonomy) · CLEAR-KGQA / Wen et al. (Bayesian
entropy scorer) · AmbiSQL / Ding et al. (taxonomy, CQ generation) · AmbiQT / Bhaskar et al.
(silent commitment, beam diversity) · EIG / Qiu et al. (interactive disambiguation basis).
