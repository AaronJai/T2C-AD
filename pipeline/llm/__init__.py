# pipeline/llm/__init__.py
from pipeline.llm.base import BaseLLM, Completion, GenerationConfig
from pipeline.llm.huggingface import HuggingFaceLLM
from pipeline.llm.openai import OpenAILLM
from pipeline.llm.anthropic import AnthropicLLM

_BACKENDS = {"huggingface": HuggingFaceLLM, "openai": OpenAILLM, "anthropic": AnthropicLLM}


def build_llm(spec: dict) -> BaseLLM:
    """Construct a backend from a config dict, e.g.
        {"backend": "huggingface", "model_name_or_path": "...", "peft_adapter_path": "..."}
        {"backend": "openai", "model": "gpt-4o"}
    All keys except 'backend' are passed through as constructor kwargs.
    """
    spec = dict(spec)
    backend = spec.pop("backend")
    if backend not in _BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}; expected one of {list(_BACKENDS)}")
    return _BACKENDS[backend](**spec)
