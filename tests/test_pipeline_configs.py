"""11.4 layer 3 — the QG-properties invariant, as an executable property of the test suite.

`QueryGenerator` derives `include_properties` from `prompt_style`, so a LOCAL model on the
`completion` path is shown **none** of the schema's property names unless a pipeline config sets
`qg_include_properties: true`, while an API model on the `instruct` path gets them for free. A
stage that is given "the schema" must be given all of it — the SL already passes
`include_properties=True` on every backend, and the QG is the only stage that was ever shown less.

decisions-log 2026-07-17 reframed properties-off as a **defect, not an experimental condition**;
decisions-log 2026-08-22 records what it cost when it recurred (10.4 job 1101275: EX C1 2->14 /
C2 13->21 / C3 16->24 on external POLE when fixed, after a completed G4 run). The defect has now
been introduced twice by copying a config, and 10.7's two defences — a per-run key-set diff and a
per-run runtime assert in the G4 runner — are both per-run. This file is the third layer and the
only permanent one: it fails offline the moment anyone adds a `config/pipeline*.yaml` for a local
model without the key, including configs written long after Phase 11.

The API exemption is **asserted, not skipped**: an API config is exempt because
`_resolve_prompt_style("api") == "instruct"` makes the derived value True, and that is checked
here on the real `QueryGenerator`, so the exemption cannot quietly stop being true either.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from experiments.run_evaluation import _resolve_prompt_style
from pipeline.llm import BaseLLM, Completion, GenerationConfig
from pipeline.query_generator.generator import QueryGenerator
from pipeline.types import SchemaMapping, SchemaRepr

_REPO = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _REPO / "config"

# Every committed pipeline config. The glob deliberately skips the runners' dot-prefixed runtime
# copies (config/.pipeline_*.runtime.yaml), which are generated per job and never committed.
_PIPELINE_CONFIGS = sorted(_CONFIG_DIR.glob("pipeline*.yaml"))


def _kind(cfg: dict) -> str:
    """The registry `kind` for a config's active_model, resolved the way run_evaluation does."""
    registry = yaml.safe_load((_REPO / cfg["models_registry"]).read_text(encoding="utf-8"))
    entry = registry[cfg["active_model"]]
    return entry.get("kind", "local")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _split() -> tuple[list[Path], list[Path]]:
    local, api = [], []
    for path in _PIPELINE_CONFIGS:
        (local if _kind(_load(path)) == "local" else api).append(path)
    return local, api


_LOCAL_CONFIGS, _API_CONFIGS = _split()


class _EchoLLM(BaseLLM):
    """Returns the prompt verbatim, so the test can assert on what the QG actually built."""

    def generate(self, prompt: str, config: GenerationConfig) -> list[Completion]:
        return [Completion(text=prompt, score=0.0, rank=1)]

    def generate_chat(self, messages: list[dict], config: GenerationConfig) -> list[Completion]:
        return self.generate(messages[-1]["content"], config)


def _schema() -> SchemaRepr:
    return SchemaRepr(
        node_labels=["Person", "Incident"],
        relationship_paths=[{"type": "SUSPECTED_OF", "source": "Person", "target": "Incident"}],
        properties={"Person": ["surname"], "Incident": ["incident_id"]},
    )


def _mapping() -> SchemaMapping:
    return SchemaMapping(question="who is suspected?", committed={},
                         cypher_syntax="(p:Person)-[:SUSPECTED_OF]->(i:Incident)",
                         resolution_mode="automated")


def _qg_prompt_for(cfg: dict) -> str:
    """Build the QG exactly as run_evaluation would for this config, and render one prompt."""
    qg = QueryGenerator(_EchoLLM(),
                        prompt_style=_resolve_prompt_style(_kind(cfg)),
                        include_properties=cfg.get("qg_include_properties"))
    return qg.generate("who is suspected?", _mapping(), _schema())


def test_pipeline_configs_are_discovered():
    """A silent empty parametrisation would make every assertion below vacuous."""
    assert _PIPELINE_CONFIGS, "no config/pipeline*.yaml found"
    assert _LOCAL_CONFIGS, "no local-model pipeline config found"
    assert _API_CONFIGS, "no api-model pipeline config found"
    assert set(_LOCAL_CONFIGS) | set(_API_CONFIGS) == set(_PIPELINE_CONFIGS)


@pytest.mark.parametrize("path", _LOCAL_CONFIGS, ids=lambda p: p.name)
def test_local_pipeline_config_sets_qg_include_properties(path):
    """THE INVARIANT: every local-model pipeline config must set the key to true.

    Not "truthy" — `is True`. The QG treats `None` as "derive from prompt_style", which on the
    completion path is False, so a missing key and an explicit false are the same defect.
    """
    cfg = _load(path)
    assert cfg.get("qg_include_properties") is True, (
        f"{path.name}: local model '{cfg['active_model']}' runs the QG on the `completion` "
        f"prompt, which omits the schema's Properties block unless this config sets "
        f"qg_include_properties: true (decisions-log 2026-07-17 / 2026-08-22)."
    )


@pytest.mark.parametrize("path", _API_CONFIGS, ids=lambda p: p.name)
def test_api_pipeline_config_is_exempt_by_construction(path):
    """The API exemption is asserted, not skipped: instruct derives properties-on for free."""
    cfg = _load(path)
    assert _kind(cfg) == "api"
    assert _resolve_prompt_style("api") == "instruct"
    # The exemption is exactly this: with the key ABSENT, the derived value is still True.
    assert cfg.get("qg_include_properties") is None, (
        f"{path.name}: an api-model config setting this key explicitly is not the exempt case "
        f"this test documents — re-check it against the local invariant above."
    )


@pytest.mark.parametrize("path", _PIPELINE_CONFIGS, ids=lambda p: p.name)
def test_every_pipeline_config_shows_the_qg_the_schema_properties(path):
    """The end the invariant exists for: the rendered QG prompt carries the property names.

    Local configs reach it via the explicit key, API configs via `prompt_style: instruct` — this
    asserts the outcome both routes are for, on the real QueryGenerator rather than on the YAML.
    """
    prompt = _qg_prompt_for(_load(path))
    assert "Properties:" in prompt, f"{path.name}: QG prompt has no Properties block"
    assert "incident_id" in prompt and "surname" in prompt, (
        f"{path.name}: QG prompt omits the schema's property names")
