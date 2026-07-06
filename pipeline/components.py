"""Dependency container for one pipeline condition. Built once; injected into the orchestrator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import neo4j
from CyVer import PropertiesValidator, SchemaValidator, SyntaxValidator

from pipeline.ambiguity.prompts import AD_SYSTEM_PROMPT
from pipeline.disambiguator.prompts import DIS_SYSTEM_PROMPT
from pipeline.entity_lookup.cache import EntityCache
from pipeline.llm import BaseLLM
from pipeline.query_generator.generator import QueryGenerator
from pipeline.schema_linker.linker import SchemaLinker
from pipeline.types import SchemaRepr

if TYPE_CHECKING:  # keep import light; only needed for type hints
    from sentence_transformers import SentenceTransformer


@dataclass(kw_only=True)
class PipelineComponents:
    """All dependencies for one condition. Construct via build(); use as a context manager."""

    # Constructed stage objects (condition-specific)
    query_generator: QueryGenerator
    schema_linker: Optional[SchemaLinker] = None      # None for baseline (no SL)
    ad_llm:  Optional[BaseLLM] = None                  # None unless disambiguation_enhanced
    dis_llm: Optional[BaseLLM] = None                  # None unless disambiguation_enhanced

    # Version-specific teaching prompts for the AD/Dis stages (7.3). Default to the frozen v2
    # constants so existing callers/tests are byte-identical; the condition builders pass the
    # v3 variants for a v3 run. Threaded to the stages by the orchestrator (it holds no config).
    ad_system_prompt: str = AD_SYSTEM_PROMPT
    dis_system_prompt: str = DIS_SYSTEM_PROMPT

    # Shared graph resources
    neo4j_driver: neo4j.Driver
    database_name: Optional[str] = None                # None = server default ("neo4j")

    # CyVer validators (built once with the driver; reused across calls)
    syntax_validator: SyntaxValidator
    schema_validator: SchemaValidator
    properties_validator: PropertiesValidator

    # Entity cache (loaded once from the live graph; used only by disambiguation_enhanced)
    entity_cache: Optional[EntityCache] = None

    # Schema + options
    schema: SchemaRepr
    embedding_model: Optional["SentenceTransformer"] = None   # for the semantic evaluator fallback
    use_prefilter: bool = False

    @classmethod
    def build(
        cls,
        *,
        query_generator: QueryGenerator,
        schema_linker: Optional[SchemaLinker],
        ad_llm: Optional[BaseLLM],
        dis_llm: Optional[BaseLLM],
        neo4j_uri: str,
        neo4j_auth: tuple,
        schema: SchemaRepr,
        database_name: Optional[str] = None,
        embedding_model: Optional["SentenceTransformer"] = None,
        use_prefilter: bool = False,
        load_entity_cache: bool = True,
        entity_registry: Optional[list[dict]] = None,
        ad_system_prompt: str = AD_SYSTEM_PROMPT,
        dis_system_prompt: str = DIS_SYSTEM_PROMPT,
    ) -> "PipelineComponents":
        """Open the driver, build the three CyVer validators, optionally load the entity cache.

        Call once per condition. The driver is closed by close() / __exit__. load_entity_cache
        defaults True (the POLE graph is tiny); set False for baseline/schema_grounded if desired.
        `entity_registry` selects the entity-searchable labels/props (None → frozen v2; 7.3
        passes the v3 registry); `ad_system_prompt`/`dis_system_prompt` carry the version-specific
        teaching prompts (defaults preserve v2 behaviour).
        """
        driver = neo4j.GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)
        cache = (EntityCache.load(driver, database_name, registry=entity_registry)
                 if load_entity_cache else None)
        return cls(
            query_generator=query_generator,
            schema_linker=schema_linker,
            ad_llm=ad_llm,
            dis_llm=dis_llm,
            ad_system_prompt=ad_system_prompt,
            dis_system_prompt=dis_system_prompt,
            neo4j_driver=driver,
            database_name=database_name,
            syntax_validator=SyntaxValidator(driver),
            schema_validator=SchemaValidator(driver),
            properties_validator=PropertiesValidator(driver),
            entity_cache=cache,
            schema=schema,
            embedding_model=embedding_model,
            use_prefilter=use_prefilter,
        )

    def close(self) -> None:
        self.neo4j_driver.close()

    def __enter__(self) -> "PipelineComponents":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
