# T2C-AD Qualitative Analysis — External POLE Benchmark, Claude Sonnet 4.6, C2 vs C3 (per-question)

*Author: Aaron Tan · Run: local Neo4j Desktop (external POLE graph, `neo4j-graph-examples/pole` —
real Greater Manchester, UK street-crime data, not authored by the student), 2026-08-06,
post-9.4 temporal fix — canonical (`results/tables_claude-sonnet_pole_external_local.md`).
Single API-model run (Claude Sonnet 4.6 via API only) — no local fine-tuned Mistral column, since
Kaya was unavailable this round. Source: `results/qual_records_claude-sonnet_pole_external_local.json`
(per-question detail, 100 items × {C2, C3}) via `experiments/analyze_qualitative.py`; full
case-study dump in `results/qualitative_analysis_claude-sonnet_pole_external_local.md`. All 80
ambiguous questions, colour-coded green/red by condition: [EX](qual-comparison-tables-pole-external-claude-sonnet.docx)
(2 regressions) and [EA](qual-comparison-tables-pole-external-claude-sonnet-ea.docx) (1 regression
— see the EX-vs-EA section below).*

This companion to the Phase 9 results deck answers the same question the v3 substrate's
equivalent report asked: **is the disambiguation module (C3) resolving real ambiguity on a graph
the student didn't design, or is its EX/EA lift over the schema-grounded baseline (C2) just noise
from C3's larger retry budget?** Method: join C2 and C3 by `question_id`, bucket all 100 items into
`both_correct` / `both_wrong` / `fixed` (C2 wrong → C3 right) / `regressed` (C2 right → C3 wrong),
then read the `fixed`/`regressed` cases directly — those are the only two buckets that say
anything about the module, since `both_correct`/`both_wrong` look identical to "C3 did nothing."

---

## The narrative in one line

**7 of 100 questions flip from wrong to right, 2 flip from right to wrong under EX (1 under the
more lenient EA metric), and the flips are not evenly spread** — they concentrate on entity
(3/7) and temporal (2/7), the same two mechanism types the v3 substrate's disambiguation module
was already good at, replicating that finding on a real graph. The module's weak spot also
replicates a v3 finding almost exactly: **intent ambiguity gets fixed zero times on either
benchmark.** The one genuinely new finding on this graph is that **schema is now the hardest
type** (1/20 fixed, 19/20 both_wrong under EX) — the reverse of v3, where schema was the
module's second-best category. That inversion, and why it happens, is the main new thing this
external run teaches us.

---

## Headline: C2-right/wrong vs C3-right/wrong (EX, n=100)

| bucket | count | % of n |
|---|---|---|
| both_correct | 57 | 57.0% |
| both_wrong | 34 | 34.0% |
| **fixed** (C2✗ → C3✓) | **7** | **7.0%** |
| **regressed** (C2✓ → C3✗) | **2** | **2.0%** |

A net +7/−2 swing is one-directional in aggregate but not spotless like v3's +18/−0 — two of
those flips are worth reading closely (below), and one turns out not to be a real regression at
all once you switch to the more lenient EA metric.

## Stratified by ambiguity_type (EX)

| ambiguity_type (n=20 each, unambiguous n=20) | both_correct | both_wrong | fixed | regressed |
|---|---|---|---|---|
| entity | 15 | 1 | **3** | 1 |
| temporal | 17 | 1 | **2** | 0 |
| unambiguous | 18 | 1 | 1 | 0 |
| schema | 0 | 19 | 1 | 0 |
| intent | 7 | 12 | 0 | 1 |

Entity and temporal account for 5 of the 7 fixes — exactly the two mechanisms whose resolution is
a schema-element or property-filter choice, which is what a `SchemaMapping` is built to carry
(same read as the v3 report). **Schema inverts the v3 pattern**: there it was the second-best
category (4/20 fixed); here it's the worst (1/20 fixed, 19/20 both_wrong) — see "Where it still
struggles" below for why.

---

## EX vs EA: how many fixed/regressed under each metric

This is the question worth answering precisely, because the two metrics disagreed sharply on the
v3 substrate (EA collapsed 18 EX-fixed items down to 5) — on this external run they don't:

| | EX (`is_correct`) | EA (`matches_any_interpretation`) |
|---|---|---|
| both_correct | 57 | 63 |
| both_wrong | 34 | 29 |
| **fixed** | **7** | **7** |
| **regressed** | **2** | **1** |

**Fixed is identical under both metrics — same 7 question_ids** (`Q-POLE-E11`, `E13`, `E16`,
`S05`, `T13`, `T14`, `U04`). That's a cleaner signal than v3 gave: on v3, most of the EX "fixed"
count turned out to be C2 already satisfying *some* interpretation, so switching to EA erased
13 of the 18 apparent fixes. Here, none of the 7 fixes are an EX/EA artifact — C3's committed
answer is landing on the benchmark's actual default reading in every one of them, not just some
looser valid alternative.

**Regressed drops from 2 to 1.** The item that disappears, `Q-POLE-E02` ("What is Anne Rice's
address?"), is the interesting case: C2's unfiltered query happens to return both real Anne Rices
(matching the benchmark's "no safe default — list both" reading exactly, so EX=True). C3
correctly detects the entity duplicate (`ad_predicted_ambiguous: True`, rationale names both
NHS numbers) but then commits to *one specific* Anne Rice rather than the unfiltered default —
so it fails EX, but that specific pick still matches one of the benchmark's own named
interpretations, so it passes EA. Read one way this is a regression (C3 changed a right answer
to a wrong one); read the other way it's a correct, if non-default, resolution of a genuine
ambiguity the question itself doesn't disambiguate. `Q-POLE-I05` (intent, "aside from BL9") is a
regression under both metrics — see below.

Per-type breakdown under EA (only cells that differ from the EX table above): schema both_correct
0→5 (some default-vs-narrow schema queries that don't match the *default* interpretation exactly
still satisfy a *narrower* one); entity regressed 1→0 (the E02 case just described).

---

## What's working

**Entity ambiguity (3/20 fixed, 15/20 already both_correct — the strongest category).** Real
duplicate/collision names in this graph turn out to be an unusually clean disambiguation signal.
Representative pattern, `Q-POLE-E11` *"Where does a person with the surname Hanson currently
live?"*: C2 guesses a single interpretation and misses the other five Hansons
(`wrong_result`); C3's Ambiguity Detector reasons that the phrasing is intentionally open
("*a* person with that surname" = all of them) and broadens the query to `WHERE p.surname =
'Hanson'`, matching the benchmark's own "no safe default, list everyone" reading. `Q-POLE-E13`
*"Find the home address of Jackson"* is the opposite failure mode fixed the opposite way: C2
misreads "Jackson" as a first-name filter (wrong node/property entirely); C3's entity lookup
flags the name/type mismatch and the AD correctly reasons that "Jackson" is ambiguous between a
person's surname and several `Location` addresses containing the word, then commits to the
surname reading.

**Temporal ambiguity (2/20 fixed, 17/20 already both_correct).** This is the category 9.4's fix
directly targeted, and it shows: `Q-POLE-T13`/`T14` ("how many calls did phone X make around date
Y") both fail on C2 because the generated query only matches the `CALLER` direction of the call
graph, undercounting; C3 commits to the bidirectional `CALLER|CALLED` pattern the Disambiguator's
rewritten few-shot now teaches, matching the gold count exactly.

**Unambiguous control items don't destabilize (1/20 flips either direction on their own, no
regressions).** `Q-POLE-U04` *"Who is Betty Kennedy related to by family?"* is the one flip, and
it's a genuine finding, not noise: the AD flags it `is_ambiguous: True` (two distinct Betty
Kennedys exist) even though the benchmark labels this item unambiguous, and C3's broader,
bidirectional `FAMILY_REL` query happens to land on the correct answer anyway. Worth reading as a
benchmark-annotation edge case (mirrors the v3 report's Q-082/Q-084 finding) rather than a module
error — the taxonomy sometimes undercounts real ambiguity in "unambiguous" control items.

---

## Where it still struggles

**Schema ambiguity (1/20 fixed, 19/20 both_wrong under EX; 5/20 both_correct under EA, but still
14/20 both_wrong) — the hardest category on this graph, inverted from v3.** Two distinct failure
patterns sit inside this number. First, the digital-contact-channel items (`S01`-`S10`: "who has
X been in digital contact with" — `KNOWS_SN` vs `KNOWS_PHONE`) mostly fail on *both* C2 and C3
with the same `wrong_result`/`valid_non_default` failure modes — the channel-split distinction
described in the results deck is a subtler signal than v3's role-edge axis, and the un-fine-tuned
QG frequently picks the wrong single channel on both conditions rather than committing to the
gold's channel-aware structure. Second, the crime-connection items (`S16`-`S20`: "who/what is
connected to crime X" — a 3-4-hop join across `PARTY_TO`/`INVOLVED_IN`/`INVESTIGATED_BY`/
`OCCURRED_AT`) fail on both C2 *and* C3 with near-identical generated Cypher — this looks like a
query-generation capability ceiling on compound multi-relationship joins, not a
disambiguation-detection failure, since C3 isn't doing anything different from C2 on these items.

**Intent ambiguity (0/20 fixed on either metric, 12/20 both_wrong) — replicates the v3 finding
exactly.** `Q-POLE-I05` *"Which area recorded the most crime, after BL9?"* is the one regression
here and it's instructive: the AD correctly detects the intent ambiguity (single-arbitrary-pick
vs a real 3-way tie for second place) and the Disambiguator does attempt a structural rewrite
(`ORDER BY ... SKIP 1 LIMIT 1`), unlike a pure schema-element choice — but the rewrite itself is
subtly wrong (skip-based re-ranking isn't equivalent to the gold's per-area lookups), so C2's
simpler, coincidentally-correct default beats C3's attempted-but-flawed fix. This is a slightly
different failure shape than v3 (where intent ambiguity never even reached a fix *attempt*), but
the outcome — 0 net fixes — is the same: RETURN/ranking-shape decisions remain largely outside
what the current `SchemaMapping` contract can reliably commit to.

---

## Takeaways

- The module's core mechanism replicates across two independent graphs it wasn't designed
  around: entity and temporal ambiguity — both expressible as a schema-element or property-filter
  choice — are where disambiguation reliably earns its keep, on the synthetic v3 graph and this
  real one alike.
- Intent ambiguity is a consistent, cross-benchmark ceiling: 0/20 fixed on both v3 and this
  external run, for the same underlying reason (RETURN-clause/ranking-shape decisions aren't
  something a `SchemaMapping` can express), even though the *specific* failure mode differs
  slightly (v3: no attempt; here: an attempted-but-flawed rewrite).
- Schema ambiguity is the one category that behaves differently here than on v3, and the
  difference is diagnostic rather than a regression in the architecture: this graph's schema axis
  (digital-contact channel) and its hardest schema items (compound multi-hop crime-connection
  queries) sit closer to the query generator's capability ceiling than v3's role-edge axis did —
  a dataset-difficulty finding, not evidence the disambiguation module itself works differently
  here.
- EX and EA tell a consistent story on this run (identical fixed set), which is itself worth
  noting as a data point: the v3 EX/EA divergence was partly an artefact of how many "fixed"
  items only cleared the lenient bar, and that artefact isn't present here.

## Open threads

- Whether a schema-linking or QG improvement specifically for the digital-contact-channel axis
  and compound crime-connection joins would close the schema gap without touching the
  disambiguation module itself (the S16-S20 near-identical-C2/C3 pattern suggests this is
  upstream of disambiguation).
- Whether extending the Disambiguator's `cypher_syntax` hint to carry an explicit
  ranking/SKIP-offset convention (mirroring the day-window literal-embedding fix from 9.4) would
  turn `Q-POLE-I05`'s attempted-but-flawed rewrite into a correct one.
- `Q-POLE-U04`'s benchmark-annotation edge case (a genuinely ambiguous "unambiguous" control item)
  is worth a note in the limitations section, alongside v3's Q-082/Q-084 — a second, independent
  instance of the same taxonomy-undercounting pattern.
