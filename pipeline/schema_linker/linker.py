# pipeline/schema_linker/linker.py
"""Schema Linker stage: fine-tuned LLM + diverse beam search → CandidateMapping."""
from __future__ import annotations

from typing import Optional

from pipeline.llm import BaseLLM
from pipeline.schema_linker.inference import sl_generation_config, sl_sampling_config
from pipeline.schema_linker.postprocessing import build_candidate_mapping
from pipeline.schema_linker.prompts import (   # build_sl_prompt is SHARED with training (1.2)
    build_sl_prompt,
    build_sl_prompt_api,
)
from pipeline.types import CandidateMapping, SchemaRepr


class SchemaLinkerError(Exception):
    """Raised when fewer than min_valid_beams parseable beams are produced."""


class SchemaLinker:
    """LLM + candidate-distribution decoding. Backend injected (BaseLLM).

    Decoding is backend-aware. The default — and the local fine-tuned path — is diverse beam
    search (`decoding=None`/`strategy="beam"`), unchanged. An API backend (no beam groups /
    logprobs) instead samples `beam_k` completions at temperature: pass
    ``decoding={"strategy": "sample", "temperature": ..., "top_p": ...}``. In both modes
    `beam_k` is the number of completions requested and the divisor for entropy normalisation,
    so the rest of the pipeline is identical.

    `prompt_style` selects the prompt (8.1): "completion" (default) uses the shared
    train/inference `build_sl_prompt` — the local fine-tuned path, unchanged; "instruct" uses
    the additive `build_sl_prompt_api` (explicit output contract + few-shots) for an API model.
    """

    def __init__(self, llm: BaseLLM, beam_k: int = 5,
                 diversity_penalty: float = 1.0, min_valid_beams: int = 1,
                 *, decoding: Optional[dict] = None, prompt_style: str = "completion"):
        self.llm = llm
        self.beam_k = beam_k
        self.min_valid_beams = min_valid_beams
        self._build_prompt = build_sl_prompt_api if prompt_style == "instruct" else build_sl_prompt
        if (decoding or {}).get("strategy") == "sample":
            self._config = sl_sampling_config(
                num_samples=beam_k,
                temperature=decoding.get("temperature", 1.0),
                top_p=decoding.get("top_p", 1.0),
            )
        else:
            self._config = sl_generation_config(beam_k, diversity_penalty)

    def link(self, question: str, schema: SchemaRepr) -> CandidateMapping:
        prompt = self._build_prompt(question, schema.to_prompt_string(include_properties=True))
        completions = self.llm.generate(prompt, self._config)
        return build_candidate_mapping(
            question, completions, schema, min_valid_beams=self.min_valid_beams
        )
