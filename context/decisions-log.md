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

---

### Example of a good entry (delete once real entries exist)

| Date | Step | Spec said | What we did | Why |
|------|------|-----------|-------------|-----|
| 2026-01-15 | 3.7 | `cyver_validator` returns `properties_score: float` | Allowed `None` when the query accesses no properties | CyVer's `PropertiesValidator.validate()` returns `None` (not a score) for property-free queries; forcing a float would misreport. Type already `Optional[float]` in 0.1, so no downstream change. |

_No real entries yet._
