# pipeline/llm/huggingface.py
from __future__ import annotations

from typing import Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from pipeline.llm.base import BaseLLM, Completion, GenerationConfig


class HuggingFaceLLM(BaseLLM):
    """Local model via transformers + optional PEFT/LoRA adapter."""

    def __init__(
        self,
        model_name_or_path: str,                    # repo id or local path — REQUIRED, never defaulted
        peft_adapter_path: Optional[str] = None,
        device_map: str = "auto",
        load_in_4bit: bool = False,
        load_in_8bit: bool = False,
        torch_dtype: str = "bfloat16",
    ):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        quant = None
        if load_in_4bit:
            quant = BitsAndBytesConfig(load_in_4bit=True,
                                       bnb_4bit_compute_dtype=getattr(torch, torch_dtype))
        elif load_in_8bit:
            quant = BitsAndBytesConfig(load_in_8bit=True)

        self.model = AutoModelForCausalLM.from_pretrained(
            model_name_or_path,
            device_map=device_map,
            torch_dtype=getattr(torch, torch_dtype),
            quantization_config=quant,
        )
        if peft_adapter_path:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, peft_adapter_path)
        self.model.eval()

    def _gen_kwargs(self, config: GenerationConfig) -> dict:
        kw = dict(
            max_new_tokens=config.max_new_tokens,
            do_sample=config.do_sample,
            num_beams=config.num_beams,
            num_return_sequences=config.num_return_sequences,
            repetition_penalty=config.repetition_penalty,
            return_dict_in_generate=True,
            output_scores=True,
            pad_token_id=self.tokenizer.pad_token_id,
        )
        if config.do_sample:
            kw.update(temperature=config.temperature, top_p=config.top_p)
        if config.num_beam_groups > 1:                      # diverse beam search
            kw.update(num_beam_groups=config.num_beam_groups,
                      diversity_penalty=config.diversity_penalty)
        return kw

    def _decode(self, prompt: str, outputs) -> list[Completion]:
        prompt_len = self.tokenizer(prompt, return_tensors="pt").input_ids.shape[1]
        gen = outputs.sequences[:, prompt_len:]
        texts = self.tokenizer.batch_decode(gen, skip_special_tokens=True)
        # Uniform log-prob scoring across greedy/beam/sample via transition scores.
        beam_indices = getattr(outputs, "beam_indices", None)
        trans = self.model.compute_transition_scores(
            outputs.sequences, outputs.scores, beam_indices, normalize_logits=True
        )
        finite = torch.where(torch.isfinite(trans), trans, torch.zeros_like(trans))
        scores = finite.sum(dim=1).tolist()
        ranked = sorted(
            (Completion(text=t, score=s, rank=0) for t, s in zip(texts, scores)),
            key=lambda c: c.score, reverse=True,
        )
        for i, c in enumerate(ranked):
            c.rank = i + 1
        return ranked

    @torch.no_grad()
    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        outputs = self.model.generate(**inputs, **self._gen_kwargs(config))
        return self._decode(prompt, outputs)

    @torch.no_grad()
    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        if self.tokenizer.chat_template:
            prompt = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"
        return self.generate(prompt, config)
