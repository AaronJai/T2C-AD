# pipeline/entity_lookup/cache.py
"""In-memory cache of entity-searchable KG nodes, loaded once from live Neo4j."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import neo4j

from pipeline.entity_lookup.registry import ENTITY_REGISTRY


@dataclass
class CachedNode:
    node_id: str
    label: str
    name_values: list[str]      # all non-null name_prop values
    display_name: str           # first non-null name_prop value
    extra: dict[str, str]       # extra_props for disambiguation context


class EntityCache:
    """Immutable cache of CachedNodes, indexed by label.

    CONTRACT: built once per PipelineComponents (5.1) from a live driver via `load`,
    immutable thereafter. `for_labels` returns the nodes for the given labels.
    """

    def __init__(self, nodes: list[CachedNode]):
        self.nodes = nodes
        self._by_label: dict[str, list[CachedNode]] = {}
        for n in nodes:
            self._by_label.setdefault(n.label, []).append(n)

    def for_labels(self, labels: list[str]) -> list[CachedNode]:
        """All cached nodes whose label is in `labels` (deduped by label list order)."""
        out: list[CachedNode] = []
        for label in labels:
            out.extend(self._by_label.get(label, []))
        return out

    @classmethod
    def load(cls, driver: neo4j.Driver, database_name: Optional[str] = None) -> "EntityCache":
        """One Cypher query per registered label; build CachedNodes.

        Reads real property *values* from the running database (not the schema file).
        Skips nodes with no non-null name value. Loaded once per PipelineComponents (5.1),
        immutable thereafter.
        """
        session_kwargs = {"database": database_name} if database_name else {}
        nodes: list[CachedNode] = []
        with driver.session(**session_kwargs) as session:
            for entry in ENTITY_REGISTRY:
                label = entry["label"]
                id_prop = entry["id_prop"]
                name_props = entry["name_props"]
                extra_props = entry["extra_props"]

                return_items = [f"n.`{id_prop}` AS node_id"]
                return_items += [f"n.`{p}` AS name_{i}" for i, p in enumerate(name_props)]
                return_items += [f"n.`{p}` AS extra_{i}" for i, p in enumerate(extra_props)]
                query = f"MATCH (n:`{label}`) RETURN " + ", ".join(return_items)

                for record in session.run(query):
                    name_values: list[str] = []
                    for i in range(len(name_props)):
                        value = record[f"name_{i}"]
                        if value is not None and str(value).strip():
                            name_values.append(str(value))
                    if not name_values:
                        continue  # no name to match against — skip

                    extra: dict[str, str] = {}
                    for i, prop in enumerate(extra_props):
                        value = record[f"extra_{i}"]
                        if value is not None:
                            extra[prop] = str(value)

                    node_id = record["node_id"]
                    nodes.append(
                        CachedNode(
                            node_id=str(node_id) if node_id is not None else "",
                            label=label,
                            name_values=name_values,
                            display_name=name_values[0],
                            extra=extra,
                        )
                    )
        return cls(nodes)
