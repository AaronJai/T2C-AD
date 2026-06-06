# pipeline/types.py
"""Shared data contracts exchanged between pipeline stages. Single source of truth."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

# ── Canonical type literals ────────────────────────────────────────────────────
AmbiguityType  = Literal["schema", "entity", "intent", "temporal"]
ElementType    = Literal["node_label", "relationship_type", "property"]
ResolutionMode = Literal["automated", "interactive"]
RoutingTarget  = Literal["query_generator", "schema_linker", "accept"]
FailureMode    = Literal["invalid_query", "valid_non_default", "wrong_result"]
Condition      = Literal["baseline", "schema_grounded", "disambiguation_enhanced"]
SchemaFormat   = Literal["nodes_and_paths", "full", "only_paths"]


# ── Schema representation ──────────────────────────────────────────────────────
@dataclass
class SchemaElement:
    """A single addressable element of the schema."""
    element_type: ElementType
    name: str                            # "SUSPECTED_OF", "Person", "crime_type"
    source_label: Optional[str] = None   # relationship source, e.g. "Person"
    target_label: Optional[str] = None   # relationship target, e.g. "Incident"
    parent: Optional[str] = None         # property's owning node/rel label


@dataclass
class SchemaRepr:
    """Serialised schema for LLM prompt injection (Mandilara 'nodes_and_paths' format).

    Properties are carried so the Schema Linker / Query Generator can include them;
    the Ambiguity Detector omits them to save context.
    """
    node_labels: list[str]
    relationship_paths: list[dict[str, str]]   # [{type, source, target}, ...]
    properties: dict[str, list[str]]           # {label: [prop_names]}
    format: SchemaFormat = "nodes_and_paths"

    def to_cypher_syntax(self) -> str:
        """Render relationship paths only, one per line:
            (Person)-[:SUSPECTED_OF]->(Incident)
        """
        return "\n".join(
            f"({p['source']})-[:{p['type']}]->({p['target']})"
            for p in self.relationship_paths
        )

    def to_prompt_string(
        self,
        include_properties: bool = False,
        max_paths: Optional[int] = None,
    ) -> str:
        """Render as the 'nodes_and_paths' block for prompts.

        include_properties=True appends per-label property lists (Schema Linker,
        Query Generator). max_paths truncates the path list (cosine pre-filter output).
        """
        node_line = "Nodes: " + ", ".join(self.node_labels)
        path_lines = [
            f"({p['source']})-[:{p['type']}]->({p['target']})"
            for p in self.relationship_paths[:max_paths]
        ]
        result = node_line + "\nPaths:\n" + "\n".join(path_lines)
        if include_properties:
            prop_block = "\nProperties:\n"
            for label, props in self.properties.items():
                prop_block += f"  {label}: {', '.join(props)}\n"
            result += prop_block
        return result


# ── Schema Linker output ───────────────────────────────────────────────────────
@dataclass
class SchemaCandidate:
    """One beam-derived candidate for an NL mention.

    score = normalised product of output-token probabilities for this beam,
    read from SFT logits (no separate perplexity pass). Beams sum to ~1.0.
    """
    element: SchemaElement
    score: float        # normalised probability ∈ (0, 1]
    beam_rank: int      # 1 = highest-scoring beam


@dataclass
class CandidateMapping:
    """Schema Linker output.

    CONTRACT: a candidate *distribution*, never an argmax. Each NL surface mention
    maps to ≥1 SchemaCandidate, ordered by score descending. The linker commits to
    nothing — that is the Disambiguator's job.
    """
    question: str
    mentions: dict[str, list[SchemaCandidate]]
    # "connected to" → [SUSPECTED_OF(0.42), WITNESSED(0.31), VICTIM_OF(0.18), INVESTIGATES(0.09)]
    beam_k: int = 5

    def top1_mapping(self) -> "SchemaMapping":
        """Top-1 candidate per mention — the unambiguous / schema-grounded shortcut."""
        committed = {
            mention: candidates[0].element
            for mention, candidates in self.mentions.items()
        }
        return SchemaMapping(
            question=self.question,
            committed=committed,
            cypher_syntax=_build_cypher_pattern(committed),
            resolution_mode="automated",
        )


# ── Entity Lookup output ───────────────────────────────────────────────────────
@dataclass
class EntityCandidate:
    """A KG instance candidate for an NL entity mention."""
    node_label: str         # "Person"
    node_id: str            # "PER-007"
    display_name: str       # "James Whitfield"
    match_score: float      # fuzzy match score ∈ [0, 1]
    posterior_score: float  # normalised Bayesian posterior (match × prior)


@dataclass
class EntityLookupResult:
    """All KG instance candidates for the entity mentions in a question."""
    question: str
    entity_mentions: dict[str, list[EntityCandidate]]
    # "James" → [PER-007(0.61), PER-013(0.39)]; ordered by posterior_score desc


# ── Ambiguity Detector output ──────────────────────────────────────────────────
@dataclass
class AmbiguityResult:
    """Bayesian scorer (secondary) + LLM self-assessment (primary), combined.

    The entropy scores inform the LLM prompt; the LLM makes the final call. Temporal
    and intent ambiguity are not reliably captured by entropy and rely on the LLM.
    Thresholds are starting points; grid-searched on the benchmark.
    """
    is_ambiguous: bool
    detected_types: list[AmbiguityType]    # may be multiple, e.g. ["schema", "temporal"]
    schema_entropy: float                  # normalised H over schema candidates ∈ [0, 1]
    entity_entropy: float                  # normalised H over entity candidates ∈ [0, 1]
    llm_rationale: str                     # raw LLM explanation (analysis/logging)
    threshold_schema: float = 0.6
    threshold_entity: float = 0.8


# ── Disambiguator output ───────────────────────────────────────────────────────
@dataclass
class SchemaMapping:
    """A committed single interpretation, serialised in Cypher syntax for the QG.

    The original NL question is carried unchanged; cypher_syntax is a prompt hint.
    Example cypher_syntax:
        (p:Person)-[:SUSPECTED_OF]->(i:Incident {incident_id})
    """
    question: str                              # original NL question, unchanged
    committed: dict[str, SchemaElement]        # NL mention → committed element
    cypher_syntax: str                         # injected into the QG prompt
    resolution_mode: ResolutionMode
    clarification_qa: Optional[tuple[str, str]] = None  # (question posed, user answer)


# ── CyVer output ───────────────────────────────────────────────────────────────
@dataclass
class ValidationResult:
    """Deterministic CyVer 3-stage validation result.

    Routing:
      syntax_valid=False                        → route_to="query_generator"
      schema_score < 1.0                        → route_to="schema_linker"
      properties_score not None and < 1.0       → route_to="schema_linker"
      all pass                                  → route_to="accept"

    properties_score is None when the query accesses no properties (CyVer returns None).
    metadata carries CyVer's per-validator diagnostic dicts.
    """
    syntax_valid: bool
    schema_score: float
    properties_score: Optional[float]
    error_type: Optional[Literal["syntax", "schema", "properties"]]
    route_to: RoutingTarget
    metadata: list[dict] = field(default_factory=list)


# ── DB Executor output ─────────────────────────────────────────────────────────
@dataclass
class ExecutionResult:
    success: bool
    result_set: list[dict]                 # list of Neo4j record dicts
    error: Optional[str]
    execution_time_ms: Optional[float]


# ── Benchmark item ─────────────────────────────────────────────────────────────
@dataclass
class BenchmarkItem:
    """One row of benchmark-updated.json (already canonical: no remapping needed).

    ambiguity_type is None when is_ambiguous is False; otherwise one of the four
    canonical types. interpretations is empty for unambiguous questions.
    """
    question_id: str
    question: str
    num_hops: int
    is_ambiguous: bool
    ambiguity_type: Optional[AmbiguityType]
    default_interp: str
    cypher_default: str
    interpretations: list[dict[str, str]]   # [{"interp": ..., "cypher": ...}]


# ── Semantic Evaluator output ──────────────────────────────────────────────────
@dataclass
class EvaluationResult:
    """Per-question evaluation, compatible with all three conditions.

    Failure modes: invalid_query (CyVer failed, never executed) /
    valid_non_default (executed; matches a non-default interpretation) /
    wrong_result (executed; matches no annotation).
    """
    question_id: str
    condition: Condition
    is_correct: bool                           # EX: matches default interpretation
    matches_any_interpretation: bool           # relaxed AREA
    ambiguity_type: Optional[AmbiguityType]    # for stratification
    failure_mode: Optional[FailureMode]
    generated_cypher: str
    cyver_result: Optional[ValidationResult]
    retry_count: int
    is_first_attempt: bool = False             # True on the first-ever attempt per question


# ── Pipeline state (orchestrator-managed) ──────────────────────────────────────
@dataclass
class PipelineState:
    """Mutable state for one pipeline run. Owned and mutated by the orchestrator."""
    question: str
    benchmark_item: Optional[BenchmarkItem]
    condition: Condition

    # Stage outputs, populated in order
    filtered_schema:    Optional[SchemaRepr]         = None
    candidate_mapping:  Optional[CandidateMapping]   = None
    entity_lookup:      Optional[EntityLookupResult] = None
    ambiguity_result:   Optional[AmbiguityResult]    = None
    schema_mapping:     Optional[SchemaMapping]      = None
    generated_cypher:   Optional[str]                = None
    validation_result:  Optional[ValidationResult]   = None
    execution_result:   Optional[ExecutionResult]    = None
    evaluation_result:  Optional[EvaluationResult]   = None

    # Retry tracking
    retry_count: int = 0
    is_failed: bool = False
    failure_reason: Optional[str] = None

    # Semantic-mismatch carry-forward. Accumulates every SchemaMapping committed in
    # this run. CLEARED on a Schema Linker outer-loop reset (new CandidateMapping);
    # NOT cleared on a disambiguation retry (same CandidateMapping — tells the
    # Disambiguator what to avoid).
    previously_tried_mappings: list[SchemaMapping] = field(default_factory=list)

    # Detection-F1 support: (question_id, AD_predicted_is_ambiguous). Condition 3 only.
    ad_predictions: list[tuple[str, bool]] = field(default_factory=list)

    MAX_SCHEMA_RETRIES: int = field(default=3, init=False)
    MAX_SYNTAX_RETRIES: int = field(default=2, init=False)
    MAX_DIS_RETRIES:    int = field(default=1, init=False)


# ── Shared serialiser ──────────────────────────────────────────────────────────
def _build_cypher_pattern(committed: dict[str, SchemaElement]) -> str:
    """Render a committed mention→element mapping as a Cypher-pattern HINT.

    Used by CandidateMapping.top1_mapping() and reused by the Disambiguator (3.5) so
    there is one source of truth for committed→syntax. The result is a *prompt hint*
    for the Query Generator, not an executed query — minor imperfections are tolerable.

    Rules:
      - Each relationship element → `(src:Source)-[:TYPE]->(tgt:Target)`, using its
        source_label/target_label.
      - Property elements are attached to the node whose label equals the property's
        `parent`, as a value-less filter hint: `(i:Incident {crime_type})`. The QG fills
        the value from the question.
      - Node-label elements not referenced by any relationship → standalone `(:Label)`.
      - Fragments are emitted relationships-first (in committed insertion order), then
        standalone nodes, joined by ", ".

    LIMITATION (flagged, see spec 0.1 §Edge cases): branching topologies are emitted as
    separate comma-joined fragments, not one connected path. Acceptable for the POLE
    benchmark (mostly linear 1–5 hop paths; this is a hint, not executed).
    """
    rels = [e for e in committed.values() if e.element_type == "relationship_type"]
    nodes = [e for e in committed.values() if e.element_type == "node_label"]
    props = [e for e in committed.values() if e.element_type == "property"]

    def _var(label: str) -> str:
        return label[0].lower() if label else "n"

    def _prop_suffix(label: str) -> str:
        names = [p.name for p in props if p.parent == label]
        return (" {" + ", ".join(names) + "}") if names else ""

    fragments: list[str] = []
    referenced: set[str] = set()
    for r in rels:
        src, tgt = r.source_label or "", r.target_label or ""
        referenced.update({src, tgt})
        fragments.append(
            f"({_var(src)}:{src}{_prop_suffix(src)})"
            f"-[:{r.name}]->"
            f"({_var(tgt)}:{tgt}{_prop_suffix(tgt)})"
        )
    for n in nodes:
        if n.name not in referenced:
            fragments.append(f"({_var(n.name)}:{n.name}{_prop_suffix(n.name)})")
    return ", ".join(fragments)
