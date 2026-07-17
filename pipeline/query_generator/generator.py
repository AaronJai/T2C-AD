# pipeline/query_generator/generator.py
"""Query Generator inference. SFT adapter for C2/C3; zero-shot base for C1."""
from __future__ import annotations

import re
from typing import Optional

from pipeline.llm import BaseLLM, GenerationConfig
from pipeline.query_generator.prompts import build_qg_prompt, build_qg_prompt_api
from pipeline.types import SchemaMapping, SchemaRepr


class QueryGenerator:
    """`prompt_style` (Phase 8 follow-up, mirrors SchemaLinker's 8.1 pattern): "completion"
    (default) is the shared train/inference prompt, `include_properties=False` — unchanged,
    byte-identical to pre-fix behaviour, required for the local fine-tuned QG's train/inference
    match. "instruct" is for an API model with no fine-tuning to protect: it gets
    `include_properties=True` (the properties block the SL already receives) and the additive
    few-shot prompt (`build_qg_prompt_api`), reusing Phase 7.4's training examples. Never used
    for C1 (build_condition1 never passes this kwarg) — the zero-shot baseline stays the
    Ozsoy-comparable format on every backend.

    `include_properties` overrides the value `prompt_style` would derive, for the QG prompt
    only (the SL already passes True on every backend — linker.py). Default None keeps the
    derived value, so every existing call site stays byte-identical. Set True on the
    "completion" path for the properties ablation (decisions-log 2026-07-17): the local QG is
    the one stage never shown the schema's property list, and 14 of the v3 schema's 24
    properties appear zero times in its SFT completions (data/pole_qg_train.jsonl), leaving it
    no source for those names at all. This makes POLE-content-with-properties a prompt the
    fine-tuned QG never saw in training (its Ozsoy replay rows are property-rich, so the
    format is in-distribution, but never with POLE content) — that shift is what the ablation
    measures, not a defect.
    """

    def __init__(self, llm: BaseLLM, *, prompt_style: str = "completion",
                 include_properties: Optional[bool] = None):
        self.llm = llm
        self.prompt_style = prompt_style
        self.include_properties = include_properties
        self._build_prompt = build_qg_prompt_api if prompt_style == "instruct" else build_qg_prompt
        self._config = GenerationConfig(
            max_new_tokens=256,   # a full Cypher query is longer than a schema pattern
            num_beams=1,          # greedy
            do_sample=False,
        )

    def generate(self, question: str, schema_mapping: SchemaMapping, schema: SchemaRepr,
                 error_feedback: Optional[str] = None) -> str:
        committed = schema_mapping.cypher_syntax or None    # "" → zero-shot (C1)
        include_properties = (self.include_properties if self.include_properties is not None
                              else self.prompt_style == "instruct")
        prompt = self._build_prompt(
            question,
            schema.to_prompt_string(include_properties=include_properties),
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
