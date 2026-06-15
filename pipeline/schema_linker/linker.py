# pipeline/schema_linker/linker.py
"""Schema Linker stage: fine-tuned LLM + diverse beam search → CandidateMapping."""
from __future__ import annotations

from pipeline.llm import BaseLLM
from pipeline.schema_linker.inference import sl_generation_config
from pipeline.schema_linker.postprocessing import build_candidate_mapping
from pipeline.schema_linker.prompts import build_sl_prompt          # SHARED with training (1.2)
from pipeline.types import CandidateMapping, SchemaRepr


class SchemaLinkerError(Exception):
    """Raised when fewer than min_valid_beams parseable beams are produced."""


class SchemaLinker:
    """Fine-tuned LLM + diverse beam search. Backend injected (BaseLLM)."""

    def __init__(self, llm: BaseLLM, beam_k: int = 5,
                 diversity_penalty: float = 1.0, min_valid_beams: int = 1):
        self.llm = llm
        self.beam_k = beam_k
        self.min_valid_beams = min_valid_beams
        self._config = sl_generation_config(beam_k, diversity_penalty)

    def link(self, question: str, schema: SchemaRepr) -> CandidateMapping:
        prompt = build_sl_prompt(question, schema.to_prompt_string(include_properties=True))
        completions = self.llm.generate(prompt, self._config)
        return build_candidate_mapping(
            question, completions, schema, min_valid_beams=self.min_valid_beams
        )
