# pipeline/orchestrator.py
"""Drive one question through the pipeline for a condition, managing the three feedback loops."""
from __future__ import annotations

from typing import Optional

from pipeline.ambiguity.detector import ambiguity_detector
from pipeline.components import PipelineComponents
from pipeline.disambiguator.disambiguator import disambiguator
from pipeline.entity_lookup.lookup import entity_lookup
from pipeline.evaluation.semantic_evaluator import semantic_evaluator
from pipeline.execution.db_executor import db_executor
from pipeline.schema_linker.linker import SchemaLinkerError
from pipeline.types import (BenchmarkItem, Condition, PipelineState, SchemaMapping,
                            ValidationResult)
from pipeline.validation.cyver_validator import cyver_validator


def _compose_error_feedback(cypher: str, vr: ValidationResult) -> str:
    """Failed query + CyVer diagnostics → the QG retry-prompt block (1.3 error_feedback)."""
    msgs = "; ".join(str(m) for m in vr.metadata) or (vr.error_type or "validation failed")
    return f"{cypher}\nValidation errors ({vr.error_type}): {msgs}"


class Orchestrator:

    def run(self, question: str, benchmark_item: Optional[BenchmarkItem],
            condition: Condition, components: PipelineComponents) -> PipelineState:
        state = PipelineState(question=question, benchmark_item=benchmark_item, condition=condition)
        error_feedback: Optional[str] = None   # carried into QG retries; None on first attempt
        schema_fail = False                     # bound here too: a SchemaLinker break exits the
                                                # outer loop before the per-iteration reset below

        # ── OUTER: schema retry ────────────────────────────────────────────────
        for schema_attempt in range(state.MAX_SCHEMA_RETRIES + 1):
            if schema_attempt > 0:
                state.retry_count += 1
                # AMENDED: previously_tried_mappings is NOT cleared — the deterministic SL
                # reproduces the same candidate set, so persisting it is what lets the
                # Disambiguator commit a different interpretation this time around.

            # Stage 0: optional cosine pre-filter (6.1; lazy import so 5.2 predates it cleanly)
            if components.use_prefilter and components.embedding_model is not None:
                from pipeline.prefilter import cosine_prefilter
                state.filtered_schema = cosine_prefilter(question, components.schema,
                                                          components.embedding_model)
            working_schema = state.filtered_schema or components.schema

            # Stages 1–3: condition-dependent upstream
            if condition == "baseline":
                state.schema_mapping = SchemaMapping(question=question, committed={},
                                                     cypher_syntax="", resolution_mode="automated")
            else:  # schema_grounded / disambiguation_enhanced both start with the Schema Linker
                # A question the SL parses to NO in-schema beam (3.1 raises SchemaLinkerError) is a
                # per-question failure, not a fatal run abort. The SL is deterministic, so retrying
                # the outer loop reproduces the same empty beam set — record invalid_query and stop.
                try:
                    state.candidate_mapping = components.schema_linker.link(question, working_schema)
                except SchemaLinkerError:
                    state.is_failed = True
                    state.failure_reason = "schema_linker_no_valid_beams"
                    break
                if condition == "schema_grounded":
                    state.schema_mapping = state.candidate_mapping.top1_mapping()
                else:  # disambiguation_enhanced
                    state.entity_lookup = entity_lookup(question, state.candidate_mapping,
                                                        components.entity_cache)
                    state.ambiguity_result = ambiguity_detector(question, state.candidate_mapping,
                                                                state.entity_lookup, components.ad_llm)
                    if benchmark_item is not None:          # Detection-F1 support (4.2)
                        state.ad_predictions.append(
                            (benchmark_item.question_id, state.ambiguity_result.is_ambiguous))

            schema_fail = False

            # ── DISAMBIGUATION: semantic-mismatch retry ────────────────────────
            for dis_attempt in range(state.MAX_DIS_RETRIES + 1):

                # Stage 4: Disambiguator (C3 only; C1/C2 keep the mapping set above)
                # AMENDED: also invoked on schema_attempt > 0 — a schema-failed mapping
                # (now in previously_tried) must not be recommitted via the top-1 bypass.
                if condition == "disambiguation_enhanced":
                    if (state.ambiguity_result.is_ambiguous or dis_attempt > 0
                            or schema_attempt > 0):
                        new_mapping = disambiguator(
                            question, state.ambiguity_result, state.candidate_mapping,
                            state.entity_lookup, components.dis_llm,
                            previously_tried=state.previously_tried_mappings)
                        if new_mapping is None:
                            break                       # candidate set exhausted
                        state.schema_mapping = new_mapping
                    else:
                        state.schema_mapping = state.candidate_mapping.top1_mapping()
                    # record (dedup by cypher_syntax — the QG-facing string)
                    if all(m.cypher_syntax != state.schema_mapping.cypher_syntax
                           for m in state.previously_tried_mappings):
                        state.previously_tried_mappings.append(state.schema_mapping)

                # ── INNER: QG + CyVer syntax retry ─────────────────────────────
                for syntax_attempt in range(state.MAX_SYNTAX_RETRIES + 1):
                    state.generated_cypher = components.query_generator.generate(
                        question, state.schema_mapping, working_schema,
                        error_feedback=error_feedback)            # None on first attempt
                    state.validation_result = cyver_validator(state.generated_cypher, components)
                    if state.first_validation_result is None:     # set once, never overwritten
                        state.first_validation_result = state.validation_result

                    if state.validation_result.route_to == "accept":
                        error_feedback = None                     # clear on success
                        break
                    elif state.validation_result.route_to == "query_generator":
                        error_feedback = _compose_error_feedback(
                            state.generated_cypher, state.validation_result)
                        if syntax_attempt == state.MAX_SYNTAX_RETRIES:
                            state.is_failed = True
                            state.failure_reason = "max_syntax_retries_exhausted"
                        continue
                    elif state.validation_result.route_to == "schema_linker":
                        # carried into the next outer iteration's first QG call
                        error_feedback = _compose_error_feedback(
                            state.generated_cypher, state.validation_result)
                        schema_fail = True
                        break

                if state.is_failed or schema_fail:
                    break
                if state.validation_result.route_to != "accept":
                    break

                # Stage 7: execute
                state.execution_result = db_executor(
                    state.generated_cypher, components.neo4j_driver, components.database_name)

                # Stage 8: evaluate (is_first_attempt = the very first attempt for this question)
                is_first = (schema_attempt == 0 and dis_attempt == 0)
                state.evaluation_result = semantic_evaluator(
                    state.execution_result, benchmark_item, state.generated_cypher,
                    state.validation_result, condition, state.retry_count,
                    components.neo4j_driver, components.database_name,
                    embedding_model=components.embedding_model, is_first_attempt=is_first)
                state.evaluation_history.append(state.evaluation_result)   # AMENDED: per-attempt log

                # semantic-mismatch routing (C3 only)
                if (condition == "disambiguation_enhanced"
                        and state.evaluation_result.failure_mode == "wrong_result"
                        and dis_attempt < state.MAX_DIS_RETRIES):
                    continue
                break

            if not schema_fail or state.is_failed:
                break

        if schema_fail and not state.is_failed:
            state.is_failed = True
            state.failure_reason = "max_schema_retries_exhausted"

        return state
