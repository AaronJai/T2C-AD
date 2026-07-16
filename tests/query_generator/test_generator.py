"""Contract tests for the Query Generator inference (spec 3.6 acceptance criteria 1-3)."""
from __future__ import annotations

from pipeline.llm import BaseLLM, Completion, GenerationConfig
from pipeline.query_generator.generator import QueryGenerator, _clean_cypher
from pipeline.types import SchemaMapping, SchemaRepr


class EchoLLM(BaseLLM):
    """Returns the prompt verbatim, so tests can assert on what the QG built."""

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        return [Completion(text=prompt, score=0.0, rank=1)]

    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        return self.generate(messages[-1]["content"], config)


class CannedLLM(BaseLLM):
    """Returns a fixed completion regardless of the prompt."""

    def __init__(self, text: str):
        self._text = text

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        return [Completion(text=self._text, score=0.0, rank=1)]

    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        return self.generate(messages[-1]["content"], config)


def _schema() -> SchemaRepr:
    return SchemaRepr(
        node_labels=["Person", "Incident"],
        relationship_paths=[{"type": "SUSPECTED_OF", "source": "Person", "target": "Incident"}],
        properties={"Person": ["name"], "Incident": ["incident_id"]},
    )


def _mapping(cypher_syntax: str) -> SchemaMapping:
    return SchemaMapping(
        question="who is suspected?",
        committed={},
        cypher_syntax=cypher_syntax,
        resolution_mode="automated",
    )


def test_committed_pattern_prompt() -> None:
    """Criterion 1: cypher_syntax != "" builds the committed-pattern prompt."""
    qg = QueryGenerator(EchoLLM())
    pattern = "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"
    prompt = qg.generate("who is suspected?", _mapping(pattern), _schema())
    assert "Committed pattern:" in prompt
    assert pattern in prompt


def test_zero_shot_prompt() -> None:
    """Criterion 2: cypher_syntax == "" uses the zero-shot text, no committed block."""
    qg = QueryGenerator(EchoLLM())
    prompt = qg.generate("who is suspected?", _mapping(""), _schema())
    assert "Committed pattern:" not in prompt
    assert "using the provided schema." in prompt


def test_clean_strips_fence_and_prose() -> None:
    """Criterion 3: fenced block + trailing prose reduce to the bare statement."""
    raw = (
        "Here is the query:\n"
        "```cypher\n"
        "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)\nRETURN p.name\n"
        "```\n"
        "This returns all suspects."
    )
    assert _clean_cypher(raw) == "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)\nRETURN p.name"


def test_clean_passes_plain_statement_unchanged() -> None:
    """Criterion 3: a plain unfenced statement passes through unchanged."""
    stmt = "MATCH (p:Person)-[:SUSPECTED_OF]->(i:Incident)\nRETURN p.name"
    assert _clean_cypher(stmt) == stmt


def test_clean_drops_trailing_prose_after_blank_line() -> None:
    """Trailing prose separated by a blank line is dropped (no fence)."""
    raw = "MATCH (p:Person) RETURN p\n\nThis query lists every person."
    assert _clean_cypher(raw) == "MATCH (p:Person) RETURN p"


def test_clean_unescapes_literal_newlines() -> None:
    """The Ozsoy-trained adapter emits literal `\\n` clause breaks; unescape to real newlines.

    Without this the statement carries a stray backslash and CyVer (3.7) rejects it.
    """
    raw = "MATCH (p:Person)\\nWHERE p.name = 'Whitfield'\\nRETURN p"
    assert _clean_cypher(raw) == "MATCH (p:Person)\nWHERE p.name = 'Whitfield'\nRETURN p"
    assert "\\n" not in _clean_cypher(raw)


def test_generate_returns_cleaned_completion() -> None:
    """generate() applies _clean_cypher to the backend completion."""
    qg = QueryGenerator(CannedLLM("```\nMATCH (p:Person) RETURN p\n```"))
    out = qg.generate("list people", _mapping(""), _schema())
    assert out == "MATCH (p:Person) RETURN p"


# ── Phase-8-follow-up: prompt_style selection (completion default vs instruct) ──────
def test_default_prompt_style_is_completion_no_properties_no_few_shots() -> None:
    """Default ("completion") stays byte-identical to pre-fix: no properties, no few-shots."""
    qg = QueryGenerator(EchoLLM())
    pattern = "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"
    prompt = qg.generate("who is suspected?", _mapping(pattern), _schema())
    assert "Examples:" not in prompt
    assert "Properties:" not in prompt


def test_instruct_prompt_style_includes_properties_and_few_shots() -> None:
    """"instruct" (API backend) gets include_properties=True and the API few-shot prompt."""
    qg = QueryGenerator(EchoLLM(), prompt_style="instruct")
    pattern = "(p:Person)-[:SUSPECTED_OF]->(i:Incident)"
    prompt = qg.generate("who is suspected?", _mapping(pattern), _schema())
    assert "Examples:" in prompt
    assert "Properties:" in prompt
    assert "incident_id" in prompt              # from _schema()'s Incident property list
