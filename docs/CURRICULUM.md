# T2C-AD — A Study Curriculum

> **Purpose.** This is a self-study guide to *your own* thesis project, written so you can
> walk into a supervisor meeting or a seminar and explain what the system is, why each
> piece exists, how data flows through it, and what the numbers mean. It is organised like
> a university unit: numbered **modules**, each with *learning outcomes*, the *content*, and
> *study questions / things you may be asked*.
>
> It is a companion to — not a replacement for — the canonical governance docs:
> `context/project-overview.md` (the *what/why*), `context/feature-specs/` (the *how*, per
> step), `context/progress-tracker.md` (build status + handoffs), and
> `context/decisions-log.md` (every deviation and why). Where this guide simplifies, those
> files are authoritative.

---

## How to use this guide

- **First pass (1 hour):** read Modules 0, 1, 3, 7 — that's enough to *talk about* the
  project at a high level (the claim, the domain, the flow, how it's evaluated).
- **Second pass:** Modules 2, 4, 5, 6 — the actual mechanics, component by component.
- **Before a presentation:** Module 8 (results + honest limitations) and the
  *defend-this* boxes throughout. The examiner's questions live there.
- The 📌 boxes are the things most likely to be challenged. Be able to answer them cold.

---

# Module 0 — Orientation: the research problem and the claim

**Learning outcomes.** After this module you can state, in two sentences, what the thesis
claims and why it is novel; and you can name the one architectural idea everything else
serves.

### 0.1 The one-sentence thesis

> *How can ambiguity in a natural-language question be **explicitly detected and resolved
> before** Cypher is generated over a knowledge graph — and does doing so improve execution
> accuracy over a system that silently commits to one interpretation?*

### 0.2 What "Text-to-Cypher" (T2C) is

Natural-language question → executable **Cypher** query (Neo4j's query language) → run it
against a graph database → answer. It is the graph analogue of Text-to-SQL.

### 0.3 The novel claim (memorise this framing)

Prior Text-to-Cypher / Text-to-SQL systems do **schema linking** — mapping words in the
question to schema elements (labels, relationship types, properties). The standard schema
linker takes an **argmax**: it silently picks the single most likely mapping and moves on.
If the question was ambiguous, that silent pick *is* the error, and nobody recorded that a
choice was even made.

This thesis's defensible contribution is **not** "ambiguity exists" (everyone agrees). It is:

> **Schema linking is the architectural locus of silent commitment.** Making ambiguity a
> *named, explicit pipeline event at that locus* — detect it, then deliberately resolve it —
> is what improves execution accuracy.

Concretely, the schema linker is re-engineered to emit a **candidate distribution** (a
ranked set of possible mappings with probabilities) instead of an argmax. A dedicated
**Ambiguity Detector** then decides whether the question is ambiguous, and a
**Disambiguator** deliberately commits to one interpretation — as opposed to that choice
happening invisibly inside the linker.

📌 **Defend this:** "Isn't this just beam search with extra steps?" — No. Beam search gives
you alternatives but the system still argmaxes. The contribution is treating the *act of
committing* as a first-class, inspectable stage with its own detector, its own retry loop,
and its own success metric (DSR). The novelty is architectural, not a new decoder.

### 0.4 What success means here (and what it explicitly does *not*)

This is a **7-billion-parameter** local model on a synthetic benchmark. The thesis does
**not** try to beat state-of-the-art absolute accuracy. Success is *demonstrating the
architecture works as claimed* (see Module 7.4 for the formal criteria). "Modest absolute
numbers reported honestly" is explicitly an acceptable result (project-overview §8).

📌 **Defend this:** if asked "your accuracy is near zero, is the project a failure?" — the
answer is that the *architectural* claim is evaluated by **C3 vs C2** (does explicit
disambiguation add value over silent grounding?) and by **Detection F1 / DSR**, not by
absolute EX. The absolute numbers are gated by base-model quality, which is a known,
documented, *separable* limitation (Module 8).

---

# Module 1 — The domain: knowledge graph, benchmark, ambiguity taxonomy

**Learning outcomes.** You can describe the POLE graph, the benchmark composition, and the
four ambiguity types with a concrete example of each.

### 1.1 The knowledge graph — SyntheticPoliceKG (POLE)

A **synthetic** policing knowledge graph on the **POLE** schema (Person, Object, Location,
Event). Synthetic on purpose: no privacy issues, and the ambiguities are *controlled* and
*annotated*. Defined in `SyntheticPoliceKG.cypher`, loaded into a local Neo4j (Docker /
Apptainer).

- **9 node labels:** Person, Incident, Case, Location, Vehicle, Phone, Evidence,
  Organisation, Communication.
- **28 relationship types.** Two families matter for ambiguity:
  - The four **Person→Incident** edges — `SUSPECTED_OF`, `WITNESSED`, `VICTIM_OF`,
    `INVESTIGATES` — are the primary source of **schema ambiguity** (a vague phrase like
    "connected to" could mean any of them).
  - **Temporal edges** — `LIVES_AT`, `OWNS`, `USES_PHONE`, `WORKS_FOR`,
    `ASSOCIATED_WITH` — carry `active` / `from_date` / `to_date` properties, the source of
    **temporal ambiguity** ("Where does X live?" = currently, or ever?).

📌 **Key distinction:** the `.cypher` file defines *structure* (labels, relationship types,
property names). The *actual values* (real names, addresses, IDs) live only in the loaded
database. This is why **Entity Lookup must query live Neo4j** — it matches "James" against
real `Person.name` values, which are not in the schema file.

### 1.2 The benchmark — `benchmark-updated.json`

- **125 annotated questions**, **50 ambiguous / 75 unambiguous**.
- Already canonical: `ambiguity_type ∈ {schema, entity, intent, temporal, null}`. No
  remapping/migration step exists or should be written.
- **Type distribution:** schema 13, entity 11, intent 11, temporal 15, null 75.

Each item (see `BenchmarkItem` in `pipeline/types.py`) carries:
`question_id`, `question`, `num_hops`, `is_ambiguous`, `ambiguity_type`, `default_interp`
(English), `cypher_default` (the gold Cypher for the default reading), and
`interpretations` (a list of alternative {interp, cypher} pairs — non-empty only for
ambiguous items).

A real unambiguous row (`Q-001`):
```
question:        "Who is suspected of the armed robbery on William Street?"
ambiguity_type:  None
cypher_default:  MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident {crime_type:'robbery'})
                 -[:OCCURRED_AT]->(loc_i:Location)
                 WHERE loc_i.address CONTAINS 'William Street' RETURN p.name
```

📌 **The annotations are evaluation-only.** Ambiguity type labels are **never** shown to any
LLM at inference time (project-overview §10). The system must *detect* ambiguity from schema
context alone; the labels exist only to score it afterward.

### 1.3 The four ambiguity types (know one example of each)

| Type | Meaning | Canonical example |
|---|---|---|
| **schema** | Which relationship/label does a vague phrase map to? | "Who is **connected to** the robbery?" → SUSPECTED_OF? WITNESSED? VICTIM_OF? |
| **entity** | Which *instance* does a name refer to? | "Show incidents linked to **James**." → which of N people named James? |
| **intent** | What is actually being asked / what's the relation? | "What is the **relationship between** Alice and the incident?" |
| **temporal** | Current state vs. historical? | "Who **owns** the getaway vehicle?" → owns now (`active:true`) or ever? |

The architecture *targets* schema, entity, and temporal. **Intent is acknowledged as the
hardest** and is not expected to show strong gains (success criterion §4).

---

# Module 2 — The data contracts (`pipeline/types.py`)

**Learning outcomes.** You can name the dataclass each stage emits and explain why the
schema linker's output is a *distribution*. These are the "nouns" of the whole system.

> Everything in `pipeline/types.py` is the **single source of truth**. No other module
> redefines these. Reading this file is the fastest way to understand the system, because
> every stage is just "takes contract X, returns contract Y."

### 2.1 The contract chain (data as it flows)

| Stage emits → | Dataclass | The key field |
|---|---|---|
| Schema Linker | `CandidateMapping` | `mentions: dict[str, list[SchemaCandidate]]` — each phrase → **ranked candidates with scores** (the distribution) |
| Entity Lookup | `EntityLookupResult` | `entity_mentions: dict[str, list[EntityCandidate]]` — each name → ranked KG instances with **posterior scores** |
| Bayesian Scorer | *(returns a tuple)* | `(schema_entropy, entity_entropy)`, both ∈ [0,1] |
| Ambiguity Detector | `AmbiguityResult` | `is_ambiguous`, `detected_types`, the two entropies, `llm_rationale` |
| Disambiguator | `SchemaMapping` | `committed: dict[str, SchemaElement]` + `cypher_syntax` (a prompt *hint*) |
| Query Generator | `str` | the cleaned, executable Cypher |
| CyVer | `ValidationResult` | `route_to ∈ {query_generator, schema_linker, accept}` |
| DB Executor | `ExecutionResult` | `success`, `result_set` |
| Semantic Evaluator | `EvaluationResult` | `is_correct` (EX), `matches_any_interpretation` (AREA), `failure_mode` |

### 2.2 The two foundational design choices encoded in the types

1. **`CandidateMapping` is a distribution, never an argmax.** Its docstring says so
   explicitly. This is *the* contribution made concrete in code. The convenience method
   `top1_mapping()` exists for the shortcut path (unambiguous questions / the
   schema-grounded condition), but the linker itself commits to nothing.

2. **`SchemaMapping.cypher_syntax` is a hint, not a query.** The disambiguator commits to an
   interpretation by emitting a Cypher *pattern* (e.g. `(p:Person)-[:SUSPECTED_OF]->(i:Incident)`)
   which is injected into the Query Generator's prompt. The original NL question is **never
   rewritten** (project-overview §10) — disambiguation guides generation, it doesn't replace
   the question.

### 2.3 `PipelineState` — the orchestrator's mutable scratchpad

One object per (question × condition) run. It accumulates every stage's output, the retry
counters, and — importantly for metrics — **per-attempt history**:
- `evaluation_history` — every attempt's `EvaluationResult` in order (`evaluation_result` is
  just the last entry).
- `first_validation_result` — the very first CyVer result, set once (drives "initial validity"
  and "structural repair" metrics).
- `previously_tried_mappings` — every interpretation committed so far. **Never cleared.**

📌 **Defend the "never cleared" rule** (this is subtle and your supervisor may probe it):
every stage decodes **deterministically** (`do_sample=False`). So if an outer retry re-ran
the schema linker on the same input, it would produce the *identical* candidate set. Without
remembering what was already tried, a retry would just recommit the same failed mapping —
making the retry budget a no-op. Persisting `previously_tried_mappings` is what lets a retry
deliberately pick a *different* interpretation. (Amended decision, 2026-06-10.)

---

# Module 3 — The pipeline flow, end to end

**Learning outcomes.** You can draw the flow from memory and explain the three feedback
loops and where each routing decision is made.

### 3.1 The diagram (reproduce this on a whiteboard)

```
NL question
   │
   ▼
Schema Linker ──▶ CandidateMapping         (distribution over schema patterns; never argmax)
   │
   ├─▶ Entity Lookup (live Neo4j) ──▶ EntityLookupResult   (KG instances matching names)
   │
   ▼
Bayesian Scorer ──▶ (schema_entropy, entity_entropy)
   │
   ▼
Ambiguity Detector ──▶ AmbiguityResult     (LLM self-assessment PRIMARY; entropy SECONDARY)
   │
   ▼
Disambiguator ──▶ SchemaMapping            (commits ONE interpretation; or top-1 if unambiguous)
   │
   ▼
Query Generator ──▶ Cypher
   │
   ▼
CyVer Validation ──▶ ValidationResult       (Syntax → Schema → Properties; typed routing)
   │   ├ syntax fail        ─▶ back to Query Generator   (INNER loop, ≤2)
   │   ├ schema/props fail   ─▶ back to Schema Linker     (OUTER loop, ≤3)
   │   └ accept
   ▼
DB Executor ──▶ ExecutionResult
   │
   ▼
Semantic Evaluator ──▶ EvaluationResult
       └ wrong_result (Condition 3 only) ─▶ back to Disambiguator   (DISAMBIGUATION loop, ≤1)
```

### 3.2 The three feedback loops (know the budgets and *why* each routes where it does)

| Loop | Trigger | Routes to | Budget | Costs a retry? |
|---|---|---|---|---|
| **Inner (syntax)** | CyVer syntax invalid | Query Generator (re-prompt with error feedback) | ≤ 2 | No |
| **Outer (schema)** | CyVer schema or properties score < 1.0 | Schema Linker (re-link, but try a *different* mapping) | ≤ 3 | Yes (`retry_count++`) |
| **Disambiguation (semantic)** | Result executes but is wrong (`wrong_result`) | Disambiguator | ≤ 1 | No |

📌 **The load-bearing routing decision:** a *schema/properties* validation failure routes
back to the **Schema Linker**, not just the Query Generator (project-overview §10). Rationale:
if the query references a label/property that doesn't exist in the graph, the *mapping* was
wrong, not just the surface syntax — so you must re-link, not just re-generate. This is what
makes the schema-linker the centre of gravity of the whole design.

📌 **Why retries need changed input:** because decoding is deterministic, every retry loop
*must* feed the model something different or it reproduces the identical failure. Inner loop:
CyVer's error message is composed into the QG prompt as `error_feedback`. Outer loop:
`previously_tried_mappings` forces a different interpretation. (Both are documented amendments,
2026-06-10.)

### 3.3 The unambiguous shortcut

If the Ambiguity Detector says `is_ambiguous = False`, there's nothing to resolve: the system
takes `candidate_mapping.top1_mapping()` and goes straight to query generation. The
disambiguation machinery only engages for detected-ambiguous questions in Condition 3.

---

# Module 4 — The components, in depth

**Learning outcomes.** For each stage you can state: its input, its output, the algorithm or
model behind it, and the one design subtlety that makes it non-trivial.

> Map to code: each component is a numbered build step. The spec is in
> `context/feature-specs/phaseN/`, the code in `pipeline/<package>/`.

### 4.1 Schema Linker (step 3.1, `pipeline/schema_linker/`)

- **In:** question + serialised schema. **Out:** `CandidateMapping`.
- **Model:** a **fine-tuned** LLM (LoRA adapter on top of Mistral-7B), decoded with
  **diverse beam search** (k=5 beams, a `diversity_penalty` that pushes beams apart). Beam
  scores → normalised probabilities → the candidate distribution.
- **Post-processing** (`postprocessing.py`) parses each raw beam string into a structured
  schema pattern, aligns beams into per-mention candidate slots, and normalises scores.
- **Subtlety / known issue:** the adapter's beams kept ending in a dangling `--` suffix (an
  artefact of the training-data pattern format). The parser learned to ignore it, which
  lifted coverage from 0 to 0.208 (Module 8). The deeper problem — low coverage — is a
  *training-quality* limitation, flagged upstream, not a linker-code defect.

📌 This is the most important component to understand deeply — it *is* the contribution, and
it's the current bottleneck (Module 8).

### 4.2 Entity Lookup (step 3.2, `pipeline/entity_lookup/`, needs live Neo4j)

- **In:** question + `CandidateMapping`. **Out:** `EntityLookupResult`.
- **How:**
  1. `EntityCache.load(driver)` reads all name-searchable nodes once (Person, Organisation,
     Case, Location are entity-searchable; Vehicle/Phone/Incident excluded). On the live
     graph this returns Person 35 / Organisation 5 / Case 4 / Location 18 = 62 nodes.
  2. `extract_entity_spans` pulls candidate name mentions from the question (regex for
     Operation names, multi-word proper nouns, quoted strings, known suburbs).
  3. `fuzzy_match_score` = rapidfuzz `token_set_ratio` / 100. Matches above a 0.75 threshold
     become candidates.
  4. `compute_posterior_scores` turns fuzzy scores into a **Bayesian posterior** (uniform
     prior × match likelihood, normalised to sum ≈ 1) — so the candidates form a proper
     distribution.
- **Subtlety:** when a span matches too many nodes (an over-generic span), candidates are
  truncated to top-N and the retained posteriors are **renormalised** so the distribution
  still sums to 1 (decision 2026-06-15) — required because the next stage takes *entropy* over
  these, which is only meaningful for a real distribution.

### 4.3 Bayesian Scorer (step 3.3, `pipeline/ambiguity/bayesian_scorer.py`)

- **In:** `CandidateMapping` + `EntityLookupResult`. **Out:** `(schema_entropy, entity_entropy)`.
- **What:** **normalised Shannon entropy.** For a slot with candidate probabilities
  *p₁…pₙ*, H = −Σ pᵢ log pᵢ, normalised by log n so H ∈ [0,1]. High entropy = candidates are
  spread out = ambiguous; low entropy = one candidate dominates = confident.
  - `schema_entropy` = the **max** normalised H across relationship-type slots (incl. the
    temporal `active`-variant slots).
  - `entity_entropy` = the max normalised H across entity mentions with ≥2 candidates.
  - Returns 0.0 when no slot qualifies.
- Pure arithmetic — no GPU, no DB.

📌 **Why it's only a *secondary* signal:** see Module 5.3 (the entropy probe). Entropy is
real but weak, and only captures schema/entity ambiguity — it cannot see *intent* or
*temporal* ambiguity. So it **informs** the detector's prompt but never *gates* the decision.

### 4.4 Ambiguity Detector (step 3.4, `pipeline/ambiguity/detector.py`)

- **In:** question, candidate mapping, entity lookup, an LLM. **Out:** `AmbiguityResult`.
- **How:** a **few-shot prompted LLM** is the **primary** judge. The prompt contains the
  ambiguity taxonomy, a curated POLE schema, four authored few-shot examples, the candidate
  distribution, the entity candidates, and the two entropy scores as *evidence*. The LLM
  returns JSON: `is_ambiguous`, `detected_types`, a rationale.
- **Robustness:** `_parse_ad_output` extracts and validates the JSON; if the LLM output is
  malformed it falls back to a **deterministic entropy-threshold** rule
  (`threshold_schema=0.6`, `threshold_entity=0.8`). It never raises.
- **Primary/secondary, precisely:** the LLM decides; entropy only *informs* the prompt and
  *gates the fallback*. (`AmbiguityType` labels never enter the prompt — detection is
  unsupervised at inference.)

### 4.5 Disambiguator (step 3.5, `pipeline/disambiguator/`)

- **In:** question, `AmbiguityResult`, candidate mapping, entity lookup, the
  `previously_tried` list, an LLM. **Out:** `Optional[SchemaMapping]`.
- **How:** a few-shot prompted LLM **commits one interpretation**, emitting a
  `committed` mention→element dict and a `cypher_syntax` hint. It is shown what was already
  tried (`_format_tried_block`) so a retry picks something new.
- **Fallbacks:** repeat / malformed output → deterministic "best untried candidate" by score.
  Returns `None` when no untried candidate remains (ends the loop).
- **Two modes:** `automated` (built, evaluated) and `interactive` (EIG-based clarification
  questions — a documented **stub**, `NotImplementedError`; future work, step 6.2).

### 4.6 Query Generator (step 3.6, `pipeline/query_generator/`)

- **In:** question + committed pattern + schema (+ optional `error_feedback`). **Out:**
  executable Cypher `str`.
- **Model:** a **second** fine-tuned LLM (separate LoRA adapter, `qg_adapter`), greedy
  decoding, `max_new_tokens=256`. Same `build_qg_prompt` used at training and inference (no
  train/inference skew).
- **Branching:** if `cypher_syntax != ""` → "committed pattern" prompt (Conditions 2 & 3);
  if `== ""` → zero-shot prompt (Condition 1 baseline).
- **`_clean_cypher`:** strips markdown fences, trims trailing prose, and — a documented fix —
  **unescapes literal `\n`/`\t`** that the adapter reproduces from the Ozsoy training gold
  (decision 2026-06-16). Without this every generated query would be invalid Cypher.

### 4.7 CyVer Validation (step 3.7, `pipeline/validation/`, needs live Neo4j)

- **In:** Cypher + the three pre-built CyVer validators. **Out:** `ValidationResult`.
- **Three deterministic stages, short-circuit on first failure:**
  1. **Syntax** — invalid → `route_to="query_generator"` (inner loop).
  2. **Schema** — score < 1.0 (references a non-existent label/rel) → `route_to="schema_linker"`.
  3. **Properties** — score not None and < 1.0 (non-existent property) → `route_to="schema_linker"`.
  4. All pass (or `properties_score is None`, meaning the query touches no properties) →
     `route_to="accept"`.
- CyVer (Mandilara et al.) is an external library; this module just wraps it and maps its
  diagnostics to typed routing.

### 4.8 DB Executor (step 3.8, `pipeline/execution/`, needs live Neo4j)

- **In:** Cypher + driver. **Out:** `ExecutionResult`.
- Runs the query in a managed **read** transaction with a server-side timeout (armed via
  `@neo4j.unit_of_work(timeout=...)`, decision 2026-06-16). Any Neo4j/driver error (incl.
  timeout) → `success=False` rather than a raise. **An empty result set is a legitimate
  success.**

### 4.9 Semantic Evaluator (step 4.1, `pipeline/evaluation/semantic_evaluator.py`)

- **In:** execution result, benchmark item, generated Cypher, CyVer result, condition. **Out:**
  `EvaluationResult`.
- **Scores two things by executing the gold Cypher *live* with the same driver:**
  - **EX** (`is_correct`): does the result set equal the **default** interpretation's result?
  - **AREA** (`matches_any_interpretation`): does it match **any** annotated interpretation?
- **`failure_mode`:** `invalid_query` (CyVer rejected / exec failed) / `None` (correct) /
  `valid_non_default` (matched a non-default interpretation — only possible on ambiguous
  items) / `wrong_result` (matched nothing).
- **Comparison is set-based:** result sets are compared as frozensets of value-tuples
  (order/duplicate-insensitive, floats rounded). Optional sentence-transformers cosine
  fallback for free-text fields.

📌 **The evaluator fix you must know about** (decision 2026-06-27): the comparison was
originally keyed on **column names** (`record.data()` keys like `p.name`). But the QG (trained
on Ozsoy naming) and the C1 baseline pick their own variable letters, so a *correct* answer
returned as `{'x.name': v}` never matched gold `{'p.name': v}` — making EX a strict
**lower bound**. It's now **column-name-insensitive** (compares value tuples in RETURN order).
⚠ The results currently in `results/` predate this fix and are **stale** — they must be
regenerated before any thesis use.

---

# Module 5 — Training and the entropy probe

**Learning outcomes.** You can explain LoRA/QLoRA at a whiteboard level, what the two
adapters are trained on, and what the entropy probe established.

### 5.1 The training data (Phase 1)

Both fine-tuned models train on the **Neo4j Text2Cypher 2025v1** dataset (Ozsoy et al.,
~40K examples; 35.9K train / 4.44K test, Apache-2.0). This is *generic* text→Cypher data —
**not** POLE-specific. The POLE benchmark is held out entirely for evaluation.

- **`extract_schema_pattern`** (step 1.1) parses a gold Cypher query into a canonical schema
  pattern — a depth-aware MATCH-clause parser written in-house (CyVer needs a live DB, which
  isn't available at this phase; decision 2026-06-07).
- **Schema-Linker data** (1.2): input = question + schema block; target = the schema pattern.
  Node-only rows are *dropped* (the linker must learn relationship structure).
- **Query-Generator data** (1.3): input = question + schema + committed pattern; target = the
  full gold Cypher. Node-only rows are *kept* (the QG must learn to generate single-node
  queries too). Same `seed=13` → consistent train/eval split with the SL data.

### 5.2 The fine-tuning method — LoRA / QLoRA (Phase 2, `pipeline/sft.py`)

- **LoRA (Low-Rank Adaptation):** instead of updating all 7B weights, freeze them and train
  small low-rank "adapter" matrices injected into attention layers. Tiny to train and store;
  swappable at inference.
- **QLoRA:** the frozen base is loaded in **4-bit** (quantised) to fit a 16 GB GPU; the LoRA
  adapters train in fp16 on top. On Kaya's V100s this is the *matched* inference path too
  (decision 2026-06-23).
- **Two adapters** are produced per base model, namespaced under `checkpoints/{model_key}/`:
  `sl_adapter` (schema linker) and `qg_adapter` (query generator).
- **Completion-only loss masking:** only the *target* tokens contribute to the loss (the
  prompt tokens are masked to `-100`), so the model learns to *produce* the answer, not to
  reproduce the prompt.
- Default base = **Mistral-7B**, but it is *one example* — backends are swappable by config
  (`config/models.yaml`); nothing may hardcode a model name.

📌 **The cluster reality** (worth a sentence in a seminar to show engineering depth): on
V100s, sequence length had to rise to 3584 tokens (the 2025v1 schemas render bimodally,
~40% exceed 1024), which forced micro-batch 2 × grad-accum 16, and the QG run (~106 GPU-h)
exceeds the 72 h queue limit so it's **checkpointed and chained** across two jobs. All in
`context/decisions-log.md` under 2026-06-08/09/12.

### 5.3 The entropy probe — an *established finding* (steps 2.2, 2.3)

Before building the pipeline, a probe asked: **does Shannon entropy over diverse beams carry
a reliable ambiguity signal?**

- **Result:** the signal is **weak but real and direction-correct** at 7B scale. A fine-tuned
  text2cypher model scores AUC ≈ 0.62 vs ≈ 0.49–0.53 for base models.
- **Ablations are flat** (entropy vs dominance vs normalisation all land ~0.587–0.594) — so
  the *scoring function* is not the bottleneck; **beam diversity at generation time** is.
- On the POLE-specific fine-tuned linker the probe stayed flat (didn't beat ~0.62), confirming
  the diversity ceiling.

📌 **This is the single most load-bearing finding in the project**, because it *justifies the
architecture*: since entropy alone is too weak to trust, **LLM self-assessment is the primary
ambiguity signal and entropy is secondary.** That design decision is downstream of this probe.
The `diversity_penalty` (= 0.2, chosen by fallback since no value met the coverage guardrail)
is locked in `config/schema_linker_inference.yaml`.

---

# Module 6 — Orchestration and integration (Phase 5)

**Learning outcomes.** You can explain how a single question is driven through all stages and
loops, and how the three experimental conditions are assembled from the same parts.

### 6.1 `PipelineComponents` (step 5.1, `pipeline/components.py`)

A container holding the *constructed* stage objects (schema linker, query generator, the AD/Dis
LLMs) plus shared resources (the Neo4j driver, the three CyVer validators, the entity cache,
the schema, the embedding model). `.build(...)` opens the driver, builds the validators once,
and loads the cache; it's a context manager that closes the driver on exit. Built **once per
condition**.

### 6.2 `Orchestrator` (step 5.2, `pipeline/orchestrator.py`)

`run(question, benchmark_item, condition, components) -> PipelineState`. It drives the three
feedback loops (Module 3.2) and does **condition routing**:

| Condition | What the orchestrator does |
|---|---|
| **baseline** | Empty mapping → QG zero-shot → validate → execute → evaluate |
| **schema_grounded** | Schema Linker → `top1_mapping()` → QG → … (no AD, no Dis) |
| **disambiguation_enhanced** | Schema Linker → Entity Lookup → Bayesian Scorer → AD → Disambiguator → QG → … |

It records the per-attempt data the metrics need (`first_validation_result`,
`evaluation_history`, C3 `ad_predictions`). One documented robustness deviation: if the linker
parses **zero** in-schema beams it raises `SchemaLinkerError`; the orchestrator catches it,
marks the question `invalid_query`, and moves on rather than aborting the whole run
(decision 2026-06-24).

### 6.3 Condition builders + the run harness (steps 5.3, 5.4)

- `build_condition1/2/3` (in `experiments/`) assemble a `PipelineComponents` for each
  condition. The SL/QG backends are fixed HuggingFace; the **AD/Dis backends are the config
  swap points** (default to the base model, overridable to OpenAI/Anthropic via a `build_llm`
  spec in `config/pipeline.yaml`).
- `experiments/run_evaluation.py` runs all 125 questions × 3 conditions, builds one
  `QuestionRecord` per question, computes metrics per condition, and writes
  `results/tables_{model}.md` + `results/metrics_{model}.json`.

📌 **The GPU-fit story** (shows you understand the engineering): naïvely each condition loads
2–3 full 7B models and OOMs on 2×16 GB V100s. Fixed in tiers — (Tier 1) load 4-bit/fp16 from
the registry; (then) **pin** C3's beam-k=5 schema linker to its own GPU and put QG+AD on the
other, because three independent `device_map="auto"` loads pile lopsidedly onto one card
(decisions 2026-06-23/26). Tier-2 (one shared 4-bit base + adapter-switching) is the fallback
if it pinches again.

---

# Module 7 — Evaluation design and metrics

**Learning outcomes.** You can explain the three conditions (what each *isolates*), define
every metric, and state the formal success criteria.

### 7.1 The three conditions — an ablation

| Condition | Setup | What it isolates |
|---|---|---|
| **C1 — Baseline** | Zero-shot base model, full schema in prompt, no fine-tuning | The raw base model |
| **C2 — Schema-grounded** | + fine-tuned Schema Linker & Query Generator, **no** disambiguation (silent top-1) | The effect of **Cypher-domain SFT** |
| **C3 — Disambiguation-enhanced** | + Ambiguity Detector + Disambiguator on top of C2 | The effect of **explicit disambiguation** |

📌 The whole experiment is an **ablation ladder**: C2−C1 = value of fine-tuning; **C3−C2 =
value of the thesis contribution.** That single difference (C3 vs C2, especially on the
50-question ambiguous subset) is what the thesis stands on.

### 7.2 The metrics (step 4.2, `pipeline/evaluation/metrics.py`)

- **EX (Execution Accuracy)** — *primary headline.* Does the result set match the **default**
  interpretation? Computed over all questions.
- **AREA (relaxed)** — *secondary/diagnostic.* Does it match **any** valid interpretation?
  AREA − EX tells you how often the system gave a *valid but non-default* answer (a "soft"
  failure) vs a genuinely wrong one. Because the pipeline commits to one interpretation, EX is
  the headline and AREA is the diagnostic.
- **Pass@1** — correct on the first attempt (before any retry).
- **DSR (Disambiguation Success Rate)** — of the questions the detector flagged ambiguous, how
  many did the disambiguator resolve to a correct answer? (C3 only.)
- **Detection F1** — binary: did the AD correctly classify ambiguous vs not? Precision +
  recall over the 50/75 split.
- **Per-type EX** — EX stratified by schema / entity / intent / temporal.
- **Structural / semantic repair %** — what fraction of initially-invalid queries the retry
  loops recovered. (Table 3, C2/C3 only.)

Output is three markdown tables via `format_metric_tables` (C1→C2→C3 columns; NaN renders `—`).

### 7.3 Why EX is headline but AREA matters

A high AREA with low EX means "the system understands the question but keeps choosing a
*different valid* reading than the annotator's default." That's a very different story from low
AREA ("the system is just wrong"), and it directly supports the ambiguity narrative — so
report both.

### 7.4 The formal success criteria (project-overview §9 — examiner bait)

1. **Architectural claim:** on the ambiguous subset, **C3 > C2** on AREA (and EX).
2. **Monotonic ordering:** C3 ≥ C2 ≥ C1.
3. **Detection works:** Detection F1 meaningfully above baseline, with **recall** high enough
   that ambiguous questions actually enter the loop (DSR is meaningless if recall is low).
4. **Per-type signal:** gains on schema, entity, temporal (intent acknowledged as hardest).
5. **Schema Linker carries the answer:** **Cov@5 ≥ 85%** (gold pattern in the top-5 beams) —
   the disambiguator can only pick the right reading if it's *in* the distribution.
6. **Probe confirmation:** post-SFT entropy AUC improves over ~0.62.
7. **Validity:** high KG-valid rate after CyVer; the repair loop recovers a non-trivial
   fraction of invalid queries.

📌 Know which criteria are currently **met, partially met, and unmet** — that's Module 8.

---

# Module 8 — Where the project actually stands (results + honest limitations)

**Learning outcomes.** You can give an honest, confident account of the current numbers, *why*
they are what they are, and what would move them — without being defensive.

### 8.1 The three-column comparison — the actual current results

Three full end-to-end runs exist on **the same pipeline code**:

| Column | Substrate | Model | Job | Full writeup |
|---|---|---|---|---|
| **v2-mistral** (frozen baseline) | v2 KG/benchmark — 28 rel types, accidental lexical near-synonyms | fine-tuned Mistral-7B (SFT) | 957276 | `results-walkthrough.md` |
| **v3-mistral** | v3 KG/benchmark — 11 rel types, only *designed* ambiguity | fine-tuned Mistral-7B (SFT) | 1032398 | `results-walkthrough-v3.md` |
| **v3-claude-sonnet** | v3 (same as above) | Claude Sonnet 4.6, API, **stage-presence not SFT** | 1061343 (canonical; supersedes 1055879) | `results-walkthrough-v3-claude-sonnet.md` |

v2→v3 changes the **substrate** (KG + benchmark, Module 9.1 glossary); v3-mistral→v3-claude-sonnet
changes the **model capability** (a strong instruct API model vs. a fine-tuned 7B). Holding code
fixed across all three is what lets each delta be attributed to those two axes rather than a code
change — **but "v2→v3 changes the substrate" is not itself a single variable**: a 2026-07-16
ablation (below and in `results-walkthrough-v3.md`) found it bundles the schema/benchmark redesign
*and* Phase 7.4's brand-new in-domain SFT data (which never existed for v2). Both turn out to be
real, separately-sized contributors — corrected from this doc's earlier "isolates the substrate"
framing.

### 8.2 Scorecard against the 7 success criteria (project-overview §9) — three columns

| # | Criterion | Target | v2-mistral | v3-mistral | v3-claude-sonnet |
|---|---|---|---|---|---|
| 1 | C3 > C2 on ambiguous AREA/EX | C3 higher | C3=C2=0 ❌ | AREA 31.2>27.5; schema 35>20 ✅ | **ambig-EA 57.5>50.0 ✅** |
| 2 | Monotonic C3 ≥ C2 ≥ C1 | ordered | all tied ❌ | ambig-EA monotonic 10.0<27.5<31.2; EX C3<C2 ⚠ | **EX 7.5<37.5<52.5 ✅** |
| 3 | Detection F1 + usable recall | high recall | F1 23.3, rec 15.2 ⚠ | F1 30.6, rec 19.2 ⚠ | **F1 73.9, rec 66.2 ✅** |
| 4 | Per-type C3 gains | measurable | all 0 ❌ | schema +15pt; **entity immovable** ⚠ | **schema/entity/temporal all +5-10pt ✅** |
| 5 | SL Cov@5 ≥ 85% | ≥ 0.85 | 0.208 ❌ | 0.725 ❌ (3.5×) | 0.658 ❌ (clears 0.60 gate) |
| 6 | Post-SFT entropy AUC > 0.62 | improve | 0.592 flat ❌ | **0.689 non-flat ✅** | 0.525 flat ❌ (by design) |
| 7 | High KG-valid + repair | high | 10–22% valid ⚠ | 42–66% valid, 2–5% repair ⚠ | **87–98% valid ✅ (repair now low — little left to repair)** |

claude-sonnet now meets **4 of 7 criteria outright** (#1/#2/#3/#4) — more than either mistral
column — after a QG output-contract fix (8.3) closed what was originally the "EX stuck at the
floor" gap. Its two misses (#5, #6) are both *by-design* consequences of stage-presence (no SFT to
push Cov@5 past 0.85; no need to hedge across samples so entropy stays flat), not defects.

### 8.3 The honest read per column (the script for the hard questions)

1. **v2-mistral (0/7) — the substrate was the bottleneck, and it's two separable substrate
   problems, not one.** Cov@5 = 0.208 on a schema with accidental near-synonym relationship types
   means the right interpretation was rarely even *in* the candidate distribution — nothing
   downstream (detection, disambiguation) could be fairly tested. Not a pipeline defect; every
   stage worked mechanically. A 2026-07-16 ablation later showed this 0.208 reflects *two*
   compounding problems: v2's own lexical noise, **and** the SL/QG having never seen a single
   in-domain (POLE-shaped) training example at all — v2's adapters are fine-tuned only on the
   generic Ozsoy dataset.

2. **v3-mistral (#1, #6) — fixing the substrate makes the architecture demonstrable, via two
   separable, both-real levers.** Cov@5 rises to 0.725 and, for the first time, **C3 measurably
   beats C2** on the ambiguous subset (AREA 31.2 vs 27.5; schema-type EA 35 vs 20) — the thesis's
   central claim, previously untestable, now shown. The 2026-07-16 attribution ablation (running
   the untouched, pre-7.4, generic-Ozsoy-only adapter against the *v3* schema, no new training)
   found Cov@5 = **0.483** at that midpoint — meaning the schema redesign alone (holding training
   fixed) already more than doubles v2's 0.208, and Phase 7.4's in-domain SFT adds a further,
   separate increment (0.483→0.725) on top. Both matter; neither alone explains the full gain.
   Its own weak point: the base-7B **detector under-detects** (recall 19.2%) even though the
   signal is present. A companion ablation (same base AD, varying only the SL adapter: Cov@5
   0.000/0.483/0.725 all give ~3-4/10 detection on a 10-item probe) suggests this ceiling tracks
   **AD-model capability**, not Cov@5 — it doesn't move with SL quality as long as the AD itself is
   the non-instruct base model. A follow-up full-scale ablation (the real C3 chain at all 120 items,
   SL **and** QG swapped together to the same tier) **confirmed the detection-flat finding at full
   statistical power** — F1 29.6/30.6/32.0 across the three tiers — so this one is robust, not just
   directional.

   📌 **A metric can be too coarse to carry a claim.** DSR looks like the natural way to ask "did
   the chain resolve what it flagged?" — but at recall 19.2% the detector flags only ~20 of 80
   items, so DSR moves in **5-point steps** and any 5.0-vs-0.0 spread is a **single question**.
   It is uninterpretable here and is not cited in this curriculum. The resolution question is
   carried instead by EX/EA, measured over all 120 items, which do track the training tier hard.

   A matching C2-only ablation (C2 has no AD/Dis, so it cleanly tests whether the C3-over-C2 gap is
   a full-SFT-only artefact) found the ambiguous-EA gap survives only where SL+QG are actually
   trained: **+3.7pp at full SFT, +0.0pp at generic-only, +0.0pp at no-adapter** (properties-on;
   +2.5/+1.2/+0.0 properties-off). Disambiguation becomes completely inert once SL+QG have nothing
   usable to hand it. (Caveat: n=80 ambiguous, so +3.7pp is ~3 items — read the *shape* as
   directional, not the magnitude as precise.)

   **A separate defect, found and fixed 2026-07-17.** The QG was the **only** stage never shown the
   schema's Properties list (`generator.py` derived it from `prompt_style`; the SL passes
   `include_properties=True` on every backend). Not a design choice — a stage told it is given "the
   schema" cannot be given 90% of one — and baked into data generation too (`pole_sft_data.py:569`
   SL rows *with* properties, `:571` QG rows *without*), leaving **14 of the v3 schema's 24
   properties absent from every one of the QG's 1800 SFT completions**. A 6-cell C2/C3 × 3-tier
   ablation plus a full C1+C2+C3 canonical rerun (job 1065123) shows the fix improves **every
   condition on every metric** (EA C1 4.2→10.8, C2 23.3→28.3, C3 23.3→27.5; KG-Valid +6.7 to
   +31.7pp across cells) while leaving **detection identical in all seven runs** — the check that
   the manipulation really was QG-only. The teaching point is the *shape* of the effect: it is
   **large on validity, modest on correctness** (EX flat at both weak tiers). Properties fix schema
   *conformance*, not *comprehension* — CyVer-rejected queries simply become executable-but-wrong
   ones. It also removes a **fairness confound** (claude-sonnet's QG always saw the full schema;
   mistral's never did), but does **not** close the gap: C2 EA 28.3 vs 57.5 at near-identical SL
   quality (EM@1 0.667 vs 0.650) — properties explain ~15% of it. The residual is a capability
   finding, not an artifact. **Open question:** `entity` EA is immovable at 20.0 across C2/C3 ×
   properties on/off — and C3 *has* Entity Lookup — so it is gated by neither property naming nor
   entity resolution. Cause unknown; the clearest next target.

3. **v3-claude-sonnet (now #1/#2/#3/#4 — detection AND execution accuracy both solved).**
   Swapping the AD/Dis/SL/QG backend to an instruct API model, **by config only**, lifts
   Detection F1 30.6→**73.9** and recall 19.2→**66.2** — confirming exactly what the ablation
   above predicted (AD capability, not SL quality, is the detection lever). The *first* G4 run
   (job 1055879) still left EX at a ~5% floor despite high validity, and grepping its log for
   Neo4j "property does not exist" warnings found the QG hallucinating generic property names
   (`type`, `id`, `description`, ... — none exist in the v3 schema,
   `results/property_hallucination_claude-sonnet_v3.txt`). Root cause, found by reading
   `generator.py`: it called `schema.to_prompt_string(include_properties=False)` on **every**
   backend — the QG's prompt never included the property list at all, and separately had **zero
   few-shot examples**, unlike SL/AD/Dis. The local fine-tuned QG only knows real names because
   Phase 7.4's SFT baked them into its weights; the API QG had no such source and no worked
   example of the gold's tight `RETURN p.name` projection style either.

   **This was fixed, not just diagnosed** (decisions-log 2026-07-16): a backend-conditional
   instruct prompt (`include_properties=True` + four few-shot examples reused verbatim from Phase
   7.4's own training data) for the API path only, leaving the local model's byte-identical
   train/inference prompt untouched. Re-running G4 (job 1061343) transformed C2/C3: **EX
   5.0→37.5 (C2), 4.2→52.5 (C3); EA 5.0→57.5 (C2), 5.0→62.5 (C3); DSR 0.0→49.2.** C1 barely moved
   (expected — untouched by the fix) and Detection F1 is exactly unchanged (a good sanity check).
   Criteria #1 and #2, previously floor-noise/failed, are now cleanly met. **The lesson is
   narrower than "stage-presence can't match SFT":** the QG prompt was simply under-specified
   relative to the other three LLM stages in this pipeline, and fixing that gap (cheap: a config
   flag + four reused training examples) closed most of the output-contract gap without any
   fine-tuning at all.

### 8.4 What would actually move the numbers now (updated "future work" slide)

The QG output-contract fix (8.3) and the four attribution/resolution ablations are **done**, not
future work — this list is what's genuinely still open:

- **SL coverage is still short of 0.85 on both backends** (0.725 / 0.658) — more/better
  POLE-adjacent training data, or a larger/stronger base model, would lift it further. The
  attribution ablation shows both schema quality *and* in-domain training data matter, so either
  lever (or both) would help.
- **A shape-invariant / semantic-equivalence EX** that credits `RETURN p` ≡ `RETURN p.name` when
  rows coincide is less urgent now that the QG fix closed most of the raw gap, but would still
  separate genuine remaining errors from any residual shape mismatches — a cheap, offline metrics
  change, no new runs needed.
- **Real interactive (EIG-based) disambiguation** remains a documented stub — theoretical basis
  exists (Qiu et al.), not built or evaluated.
- **The v2 baseline never got the two-factor treatment** — it would be a small, cheap addition to
  also measure v2-schema + in-domain-SFT (not run, since v2 is frozen by design), just to have the
  full 2×2 rather than the current 3-of-4 cells.

### 8.5 What is genuinely demonstrated (the positive claims, updated)

- A complete, **model-agnostic, explicit-disambiguation T2C architecture** runs end-to-end,
  unchanged in code, on **both** a local fine-tuned backend and a live API backend — the model
  swap is a one-line config change (`active_model`), nothing else.
- The schema linker **emits a real candidate distribution** in both regimes (beam search locally,
  temperature sampling for the API model) — the core contribution, in code, on two backends.
- The **ambiguity-detection premise is proven, not just argued, and its recall ceiling tracks the
  AD model rather than SL quality**: F1 73.9 / recall 66.2 on a model that never sees
  ambiguity-type labels at inference time, and an ablation (directional, n=10) shows this recall
  ceiling doesn't move with SL quality when the AD model itself is held fixed — it moves with the
  AD model. That result is scoped to detection specifically: a separate full-scale ablation shows
  SL/QG quality is very much *not* spent once you look at **resolution** (DSR 0.0 without the 7.4
  SFT vs. 5.0 with it, at flat detection) — the two findings sit side by side, not in conflict.
  A matching C2-only ablation adds the finer-grained picture: the C3-over-C2 ambiguous-EA margin
  (the thesis's central architectural claim) shrinks monotonically as SL/QG weaken (+2.5pp →
  +1.3pp → +0.0pp) rather than surviving or vanishing outright — disambiguation keeps adding some
  value down to a real floor, where it becomes measurably inert only once SL+QG can't produce
  anything usable to begin with.
- **Execution accuracy is also demonstrated, on the API backend, once one small prompt gap was
  closed** — EX 7.5/37.5/52.5, monotonically ordered, ambiguous EA C3 > C2 by a real margin
  (n=80). Stage-presence (no fine-tuning) is *not* structurally incapable of matching SFT's output
  discipline; it just needed the same information (schema properties) and the same kind of
  scaffolding (a few worked examples) every other stage in this pipeline already had.
- The **typed-routing validation loops** generalise to a very different model: with the QG fix,
  the API backend's first-draft validity (96.7–97.5% initial-valid) now *exceeds* the point of
  needing much repair at all — a stronger, cleaner result than the original "48–71% repair
  recovery" framing, which was really measuring how much repair was needed because first drafts
  were poor.
- The bottleneck has moved **three times**, each time to a different, isolated, measured, and
  separable factor, and each time it was closed: **substrate** (v2, both a schema effect and a
  missing-training-data effect) → **detector strength** (v3-mistral's base-AD ceiling, confirmed
  model-gated by ablation) → **output-contract conformance** (v3-claude-sonnet's QG prompt gap,
  fixed with a cheap prompt change). That progression — not a stuck number, but a sequence of
  cleanly diagnosed *and resolved* limitations — is itself the clean scientific result.

📌 **The sentence to land in a seminar:** *"Across three columns, the architecture's core claims
are demonstrated and, where a gap appeared, it was diagnosed down to a specific, fixable cause
rather than accepted as a structural limit: the v2→v3 substrate change turned out to be two real,
separable levers (schema design and in-domain training data); the detection ceiling turned out to
be gated by the detector model's own reasoning capability, not schema-linker quality — while
resolution, once something is flagged, remained gated by schema-linker/generator quality the whole
time, a distinction only a full end-to-end ablation could show; and the API backend's
execution-accuracy floor turned out to be a missing properties block and missing few-shot examples
in one prompt, not an inherent cost of skipping fine-tuning. Every measured gap in this project has
a named, evidenced cause — and, in the cases tested, a demonstrated fix."*

---

# Module 9 — Reference

### 9.1 Glossary

- **POLE** — Person, Object, Location, Event; the KG schema family.
- **Schema linking** — mapping NL phrases to schema elements (labels/relationships/properties).
- **Argmax commitment** — silently taking the single top mapping; the thing this thesis makes
  explicit instead.
- **Candidate distribution** — ranked mappings with probabilities (the linker's output).
- **Diverse beam search** — beam search with a penalty that pushes beams apart, to surface
  genuinely different interpretations.
- **Cov@5** — fraction of questions whose gold pattern appears in the top-5 beams.
- **EM@1** — exact match at the top-1 beam.
- **EX / AREA** — Execution Accuracy (vs default) / relaxed Any-Reasonable-interpretation Accuracy.
- **DSR** — Disambiguation Success Rate.
- **LoRA / QLoRA** — low-rank adapter fine-tuning / its 4-bit-quantised-base variant.
- **CyVer** — the external 3-stage (syntax/schema/properties) Cypher validator.
- **Shannon entropy (normalised)** — spread of a probability distribution, scaled to [0,1];
  the secondary ambiguity signal.
- **Substrate** — the KG schema + benchmark pair a run is evaluated against
  (`SyntheticPoliceKG*.cypher` + `benchmark-*.json`), as distinct from the *model* running the
  pipeline. v2→v3 is a substrate change (pipeline code fixed, only the graph/benchmark differ);
  v3-mistral→v3-claude-sonnet is a model change (same v3 substrate, different backend). Naming
  these as separate axes is what lets each result delta be attributed to one cause.
- **Stage-presence (vs. SFT)** — for an API model, C2/C3 mean "the SL/AD/Dis/QG stages run and
  are prompted accordingly," not "these stages were fine-tuned." Locked 2026-06-30: API backends
  are never fine-tuned in this project, so their C2/C3 results isolate prompting + reasoning
  capability, not domain-adapted output style.

### 9.2 Code ↔ concept map

| Concept | Spec | Code |
|---|---|---|
| Shared contracts | 0.1 | `pipeline/types.py` |
| LLM backends | 0.2 | `pipeline/llm/` |
| POLE schema | 0.3 | `pipeline/schema.py` |
| Benchmark loader | 0.4 | `pipeline/data/` |
| Training data | 1.1–1.3 | `pipeline/schema_linker/`, `pipeline/query_generator/` |
| Fine-tuning | 2.1, 2.4 | `pipeline/sft.py`, `experiments/train_*.py` |
| Entropy probe | 2.2, 2.3 | `experiments/{diversity_penalty_sweep,entropy_probe,probe_utils}.py` |
| Schema Linker | 3.1 | `pipeline/schema_linker/{inference,postprocessing,linker}.py` |
| Entity Lookup | 3.2 | `pipeline/entity_lookup/` |
| Bayesian Scorer | 3.3 | `pipeline/ambiguity/bayesian_scorer.py` |
| Ambiguity Detector | 3.4 | `pipeline/ambiguity/detector.py` |
| Disambiguator | 3.5 | `pipeline/disambiguator/` |
| Query Generator | 3.6 | `pipeline/query_generator/generator.py` |
| CyVer validation | 3.7 | `pipeline/validation/` |
| DB Executor | 3.8 | `pipeline/execution/` |
| Semantic Evaluator | 4.1 | `pipeline/evaluation/semantic_evaluator.py` |
| Metrics | 4.2 | `pipeline/evaluation/metrics.py` |
| Components / Orchestrator | 5.1, 5.2 | `pipeline/components.py`, `pipeline/orchestrator.py` |
| Condition builders / run | 5.3, 5.4 | `experiments/build_condition*.py`, `experiments/run_evaluation.py` |
| Prefilter / Gradio demo (future) | 6.1, 6.2 | `pipeline/prefilter.py`, `app/gradio_demo.py` (not started) |

### 9.3 Key papers (and what each gives this project)

- **Ozsoy et al.** — the Neo4j Text2Cypher 2025v1 dataset (training data + a baseline).
- **DTS-SQL / DIN-SQL** — decomposed fine-tuning and "schema linking is the dominant failure"
  (the Schema-Linker design + the motivation that it's where errors concentrate).
- **Hornsteiner et al.** — modular pipeline + error routing (the typed feedback loops).
- **Gusarov et al. (GraphRAG)** — schema-injection prompt format.
- **Mandilara et al. (CyVer)** — the validation component itself.
- **AmbiGraph-Eval / Tian et al.** — the AREA metric + ambiguity taxonomy.
- **CLEAR-KGQA / Wen et al.** — the Bayesian entropy scorer idea.
- **AmbiSQL / Ding et al.** — ambiguity taxonomy + clarification-question generation.
- **AmbiQT / Bhaskar et al.** — *silent commitment* + beam diversity (the core problem framing).
- **EIG / Qiu et al.** — the theoretical basis for the (future) interactive disambiguation mode.

### 9.4 Self-test — can you answer these without notes?

1. State the novel claim in one sentence, and why it isn't "just beam search."
2. Why is the schema linker's output a *distribution*, and why does `previously_tried_mappings`
   never get cleared?
3. A query references a property that doesn't exist. Which loop fires, and *why* does it route
   to the schema linker rather than the query generator?
4. Why is entropy only a *secondary* signal? What probe result justifies that?
5. What does C3 − C2 isolate, and why is it the number the thesis stands on?
6. EX is near zero. Give the honest, non-defensive explanation in three sentences.
7. What is Cov@5, what is it currently, what should it be, and why does everything downstream
   depend on it?
8. Why must Entity Lookup query the live database instead of the schema file?
9. What's the difference between a *substrate* change and a *model* change, and why does holding
   pipeline code fixed across all three columns matter to the argument?
10. Claude Sonnet lifts Detection F1 from 30.6 to 73.9. The *first* G4 run still left EX at the
    floor despite this; the *second* (post-fix) run didn't. What does "stage-presence, not SFT"
    mean, what was actually missing from the QG's prompt, and why was fixing it cheap rather than
    requiring fine-tuning?
11. The v2→v3 Cov@5 jump (0.208→0.725) and the detection-recall ceiling (~19-25% with a base AD)
    were both originally explained by a single cause each. What did the 2026-07-16 ablations show
    was actually going on in each case, and why does that matter for how confidently you can state
    either finding?
12. Showing the QG the schema's Properties list raised **KG-Valid** by up to +31.7pp but left **EX**
    flat at the weak tiers. Explain that gap in terms of what CyVer can and cannot check — and say
    why "the local model's low EX was a harness artifact" is *not* the conclusion this supports.
13. The claim "the QG couldn't name 14 of 24 properties, so 21 items were unwinnable, capping EA at
    82.5%" was a reasonable prediction that turned out to be **false** (EA went 23.3→28.3, not
    toward 82.5). What did that failure reveal about the difference between a *necessary* condition
    and a *binding* one — and which stage's numbers should you have checked first to notice that
    property naming was never the tightest constraint?

---

*Maintenance note:* this is a study aid, not a governance file. When the build advances or
numbers change, the authority is `context/progress-tracker.md`, `context/decisions-log.md`,
and a fresh `results/` run — update this guide from those, not the reverse.
