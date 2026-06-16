# pipeline/query_generator/generator.py
"""Query Generator inference. SFT adapter for C2/C3; zero-shot base for C1."""
from __future__ import annotations

import re
from typing import Optional

from pipeline.llm import BaseLLM, GenerationConfig
from pipeline.query_generator.prompts import build_qg_prompt
from pipeline.types import SchemaMapping, SchemaRepr


class QueryGenerator:
    def __init__(self, llm: BaseLLM):
        self.llm = llm
        self._config = GenerationConfig(
            max_new_tokens=256,   # a full Cypher query is longer than a schema pattern
            num_beams=1,          # greedy
            do_sample=False,
        )

    def generate(self, question: str, schema_mapping: SchemaMapping, schema: SchemaRepr,
                 error_feedback: Optional[str] = None) -> str:
        committed = schema_mapping.cypher_syntax or None    # "" → zero-shot (C1)
        prompt = build_qg_prompt(
            question,
            schema.to_prompt_string(include_properties=False),
            committed_pattern=committed,
            error_feedback=error_feedback,    # retry path only (5.2); None on first attempt
        )
        completion = self.llm.generate(prompt, self._config)[0].text
        return _clean_cypher(completion)


# Clause keywords a Cypher statement can open (or continue) with. Used both to locate the
# start of the statement in noisy base-model output and to detect its end (trailing prose).
_CYPHER_KEYWORDS = (
    "MATCH", "OPTIONAL", "RETURN", "CALL", "MERGE", "CREATE", "WITH", "UNWIND",
)
_FENCE_RE = re.compile(r"```(?:cypher)?[ \t]*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def _starts_clause(line: str) -> bool:
    upper = line.strip().upper()
    return any(upper.startswith(kw) for kw in _CYPHER_KEYWORDS)


def _clean_cypher(text: str) -> str:
    """Strip markdown code fences and any trailing prose; return the Cypher statement.

    The fine-tuned model is trained to emit only the query, but base models (C1) may add a
    fence or a trailing comment. Take the fenced block if present, else the text up to the
    first blank line after a MATCH/RETURN/CALL/MERGE/CREATE/WITH; strip whitespace.

    Also unescapes literal ``\\n`` / ``\\t`` / ``\\r`` to real whitespace: the QG adapter is
    trained on the Ozsoy text2cypher data, whose gold completions store clause breaks as the
    two-character escape ``\\n`` rather than a real newline (see decisions-log 2026-06-16), so
    the model emits ``MATCH …\\nRETURN …`` verbatim. A literal backslash is not valid Cypher
    whitespace, so without this the statement would be rejected by CyVer (3.7). Unescaping here
    keeps the downstream contract a directly executable query string.
    """
    body = text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "")

    match = _FENCE_RE.search(body)
    body = match.group(1) if match else body

    lines = body.splitlines()
    start = next((i for i, line in enumerate(lines) if _starts_clause(line)), None)
    if start is None:
        # No recognisable clause keyword (e.g. a fenced block we trust verbatim) — strip only.
        return body.strip()

    collected: list[str] = []
    for line in lines[start:]:
        if line.strip() == "":      # blank line ends the statement; trailing prose is dropped
            break
        collected.append(line)
    return "\n".join(collected).strip()
