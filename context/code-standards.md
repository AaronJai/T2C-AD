# Code Standards

Short by design. The goal is to stop style drift across sessions, not to be exhaustive.

---

## Python

- **Version:** 3.11+.
- Every module starts with `from __future__ import annotations`.
- Prefer builtin generics: `list[str]`, `dict[str, int]`, `tuple[float, float]`.
  Import `Optional`, `Literal`, `Callable`, `Protocol` from `typing` as needed.
- **Full type annotations** on every public function, method, and dataclass field.
- Use `@dataclass` for all data contracts (the pipeline passes structured objects between
  stages, not loose dicts).

## Types & contracts

- **All shared types live in `pipeline/types.py` (step 0.1).** Import them; never
  re-declare a dataclass or `Literal` that already exists there.
- `GenerationConfig` and `Completion` are the exception — they live in `pipeline/llm/base.py`
  (step 0.2) because they belong to the LLM interface, not the pipeline data flow.
- Never hardcode a model name (e.g. `"mistralai/Mistral-7B-v0.1"`) outside a config file
  or a function's default argument. Backends are selected by config.

## Docstrings

- Concise, not Google-verbose. One-line module docstring stating the module's purpose.
- Public functions/classes: a one-line summary, plus `Args:`/`Returns:` only when the
  signature isn't self-explanatory. Document non-obvious edge cases and any CONTRACT the
  caller must rely on (e.g. "returns candidates ordered by score descending; scores sum
  to ~1.0").

## Imports

Three groups, blank-line separated, alphabetised within each (isort default):

1. Standard library
2. Third-party (`neo4j`, `torch`, `transformers`, `rapidfuzz`, `sentence_transformers`, …)
3. Local (`from pipeline.types import ...`)

## Tests

- **pytest.** Tests live in `tests/`, mirroring the `pipeline/` package layout
  (`tests/schema_linker/test_postprocessing.py`, etc.).
- Each component step ships at least one **contract test**: feed a minimal hand-built
  input, assert the output type and the key invariants the spec promises (e.g. candidate
  scores sum to ~1.0; `route_to` is valid for the failure type).
- Tests that need a live Neo4j, a GPU, or a trained adapter are marked
  `@pytest.mark.integration` and skipped by default, so the fast suite runs anywhere.
- A step's spec states which acceptance checks are unit-testable now vs deferred to a
  training/eval run; the contract test covers the "now" set.

## Layout

Package root is `pipeline/`. Module paths are given in each spec and in the build map at
the foot of `progress-tracker.md`. Final deliverables and adapters go where the spec says
(`checkpoints/sl_adapter/`, `data/*.jsonl`, etc.).

## Dependencies

declare runtime dependencies in `pyproject.toml`; when a step first needs a new package, add it there