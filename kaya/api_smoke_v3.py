"""8.3 Gate G0.5 — Claude API smoke over a few v3 questions (pre-flight for the gated chain).

NOT a pipeline module: a cheap Kaya pre-flight that eyeballs the API backend end-to-end BEFORE
committing to the multi-hour G1–G4 chain. For a stratified handful of v3 questions it drives one
round-trip through each stage on the `kind: api` model and writes a plain-text report putting the
RAW model completions side-by-side with what the pipeline parses out of them:

  - SL  : k=5 temperature samples with the instruct prompt (8.1) → raw completion lines vs the
          extracted/parsed schema patterns and the aggregated CandidateMapping distribution.
  - AD  : one detector call → raw text vs the extracted JSON object (the AmbiguityResult fields).
  - Dis : one disambiguator call → raw text vs the parsed committed_pattern.
  - QG  : one query-generator call in BOTH modes (committed-pattern and zero-shot) → raw text vs
          the cleaned/extracted Cypher.

Plus two operational checks the spec calls for:
  - EGRESS: fail fast with a clear message if api.anthropic.com:443 is unreachable from the node.
  - count_tokens: measure the SL and AD/Dis prompt PREFIXES (prompt-caching viability — Sonnet 4.6
    needs a >=2048-token cacheable prefix; record the numbers). Wiring cache_control is OPTIONAL
    and out of 8.2's scope — this only records whether the prefixes clear the bar.

No Neo4j and no GPU: the AD/Dis inputs use an EMPTY EntityLookupResult (entity resolution needs a
live graph and is exercised by G3/G4, not here) so G0.5 stays a work-partition, key-only pre-flight.
Run via kaya/82_api_smoke_v3.slurm with ANTHROPIC_API_KEY exported.
"""
from __future__ import annotations

import argparse
import os
import socket
import sys
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from pipeline.ambiguity.detector import _extract_json_object as _ad_extract_json
from pipeline.ambiguity.prompts import (AD_SYSTEM_PROMPT_V3, _format_candidate_block,
                                        _format_entity_block, build_ad_user_turn)
from pipeline.ambiguity.bayesian_scorer import compute_ambiguity_scores
from pipeline.data.benchmark_loader import items_by_type, load_benchmark
from pipeline.disambiguator.disambiguator import _extract_json_object as _dis_extract_json
from pipeline.disambiguator.prompts import DIS_SYSTEM_PROMPT_V3, build_disambiguator_prompt
from pipeline.llm import GenerationConfig, build_llm
from pipeline.query_generator.generator import QueryGenerator, _clean_cypher
from pipeline.query_generator.prompts import build_qg_prompt_api
from pipeline.schema import build_pole_v3_schema_repr
from pipeline.schema_linker.inference import (extract_pattern_from_completion,
                                              sl_sampling_config)
from pipeline.schema_linker.postprocessing import build_candidate_mapping, parse_schema_pattern
from pipeline.schema_linker.prompts import build_sl_prompt_api
from pipeline.types import AmbiguityResult, EntityLookupResult, SchemaMapping

_CACHE_MIN_TOKENS = 2048          # Sonnet 4.6 minimum cacheable prefix (prompt-caching viability)


def _egress_check(host: str = "api.anthropic.com", port: int = 443, timeout: float = 10.0) -> None:
    """Fail fast with a clear message if the Anthropic API host is unreachable from this node."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            print(f"[egress] {host}:{port} reachable.")
    except OSError as exc:
        print(
            f"[egress] FATAL: cannot reach {host}:{port} from this compute node ({exc}).\n"
            f"         The API gate chain needs outbound HTTPS. Check the partition's egress "
            f"policy or run on a node with internet access.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _count_tokens(llm, text: str) -> int:
    """count_tokens for a single user turn of `text` on the API model; -1 if unavailable."""
    try:
        resp = llm.client.messages.count_tokens(
            model=llm.model, messages=[{"role": "user", "content": text}])
        return int(resp.input_tokens)
    except Exception as exc:                                  # pragma: no cover - live-only
        print(f"[count_tokens] unavailable ({exc})", file=sys.stderr)
        return -1


def _sample(items_path: str, n: int) -> list:
    """A stratified spread (evenly across ambiguity types + null) capped at n questions."""
    by_type = items_by_type(load_benchmark(items_path))
    order = ["schema", "entity", "temporal", "intent", None]
    picks: list = []
    idx = 0
    while len(picks) < n:
        advanced = False
        for key in order:
            bucket = by_type.get(key, [])
            if idx < len(bucket):
                picks.append(bucket[idx])
                advanced = True
                if len(picks) >= n:
                    break
        if not advanced:
            break
        idx += 1
    return picks[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_key", default="claude-sonnet")
    ap.add_argument("--benchmark", default="data/benchmark-v3.json")
    ap.add_argument("--models_config", default="config/models.yaml")
    ap.add_argument("--n_questions", type=int, default=6, help="stratified sample size (5–10).")
    ap.add_argument("--temperature", type=float, default=0.7, help="SL sampling temperature.")
    ap.add_argument("--report", default=None,
                    help="default results/api_smoke_{model_key}_v3.txt")
    ap.add_argument("--egress_host", default="api.anthropic.com")
    args = ap.parse_args()

    _egress_check(args.egress_host)

    with open(args.models_config) as fh:
        registry = yaml.safe_load(fh)[args.model_key]
    if registry.get("kind") != "api":
        raise SystemExit(f"api_smoke is for an `kind: api` model; '{args.model_key}' is not.")

    llm = build_llm({"backend": registry["backend"], "model": registry["model"]})

    schema = build_pole_v3_schema_repr()
    schema_block = schema.to_prompt_string(include_properties=True)
    items = _sample(args.benchmark, args.n_questions)

    # Report to a StringIO, then flush to stdout + file so nothing is lost if a stage errors.
    out = StringIO()

    def emit(line: str = "") -> None:
        out.write(line + "\n")

    emit(f"===== API smoke (v3) — model_key={args.model_key} "
         f"model={registry['model']} =====")
    emit(f"sampled {len(items)} questions; SL temperature={args.temperature}, k=5 (instruct prompt)")
    emit()

    sl_cfg = sl_sampling_config(num_samples=5, temperature=args.temperature)

    # ── count_tokens on the cacheable prefixes (prompt-caching viability) ─────────────
    sl_prefix_tokens = _count_tokens(llm, build_sl_prompt_api("", schema_block))
    ad_prefix_tokens = _count_tokens(llm, AD_SYSTEM_PROMPT_V3)
    dis_prefix_tokens = _count_tokens(llm, DIS_SYSTEM_PROMPT_V3)
    emit("----- PROMPT-CACHE PREFIX TOKENS (Sonnet 4.6 needs >= 2048 to cache) -----")
    for name, toks in (("SL instruct prefix (system+few-shots+schema)", sl_prefix_tokens),
                       ("AD system prompt (v3)", ad_prefix_tokens),
                       ("Dis system prompt (v3)", dis_prefix_tokens)):
        verdict = "n/a" if toks < 0 else ("CACHEABLE" if toks >= _CACHE_MIN_TOKENS
                                          else "below bar")
        emit(f"  {name:<48} {toks:>6}  [{verdict}]")
    emit()

    # ── Per-question SL round-trips (raw completions vs parsed patterns) ──────────────
    mappings = {}
    for it in items:
        emit(f"========== [{it.question_id}] ({it.ambiguity_type or 'null'}) ==========")
        emit(f"Q: {it.question}")
        prompt = build_sl_prompt_api(it.question, schema_block)
        completions = llm.generate(prompt, sl_cfg)
        emit("  SL raw completions  ->  extracted pattern  ->  parsed nodes/rels:")
        for c in completions:
            raw = c.text.strip().replace("\n", "\\n")
            extracted = extract_pattern_from_completion(c.text)
            try:
                parsed = parse_schema_pattern(extracted, schema, c.score)
                parsed_desc = f"nodes={parsed.nodes} rels={[r[:4] for r in parsed.relationships]}"
            except Exception as exc:                          # pragma: no cover - live-only
                parsed_desc = f"<parse error: {exc}>"
            emit(f"    raw: {raw[:140]}")
            emit(f"      extracted: {extracted[:140]}")
            emit(f"      parsed:    {parsed_desc[:160]}")
        mapping = build_candidate_mapping(it.question, completions, schema)
        mappings[it.question_id] = mapping
        emit(f"  CandidateMapping mentions ({len(mapping.mentions)} slots):")
        for slot, cands in mapping.mentions.items():
            top = ", ".join(f"{c.element.name}:{c.score:.2f}" for c in cands[:3])
            emit(f"    {slot}: {top}")
        emit()

    # Pick an ambiguous item (fallback to the first) to exercise AD/Dis/QG once each.
    focus = next((it for it in items if it.is_ambiguous), items[0])
    fm = mappings[focus.question_id]
    empty_el = EntityLookupResult(question=focus.question, entity_mentions={})   # no Neo4j in G0.5
    schema_entropy, entity_entropy = compute_ambiguity_scores(fm, empty_el)

    # ── AD round-trip (raw text vs parsed JSON) ──────────────────────────────────────
    emit(f"========== AD call on [{focus.question_id}] ==========")
    ad_user = build_ad_user_turn(focus.question, _format_candidate_block(fm),
                                 _format_entity_block(empty_el), schema_entropy, entity_entropy)
    ad_raw = llm.generate_chat(
        [{"role": "system", "content": AD_SYSTEM_PROMPT_V3},
         {"role": "user", "content": ad_user}],
        GenerationConfig(max_new_tokens=256, do_sample=False))[0].text
    ad_obj = _ad_extract_json(ad_raw)
    emit(f"  raw:    {ad_raw.strip()[:400]}")
    emit(f"  parsed: {ad_obj}")
    emit()

    # Build an AmbiguityResult from the parsed AD output (or a permissive default) for Dis.
    if ad_obj and "is_ambiguous" in ad_obj:
        detected = [t for t in ad_obj.get("detected_types", [])
                    if t in {"schema", "entity", "intent", "temporal"}]
        ad_result = AmbiguityResult(
            is_ambiguous=bool(ad_obj["is_ambiguous"]),
            detected_types=detected if ad_obj["is_ambiguous"] else [],
            schema_entropy=schema_entropy, entity_entropy=entity_entropy,
            llm_rationale=str(ad_obj.get("rationale", "")))
    else:
        ad_result = AmbiguityResult(
            is_ambiguous=True, detected_types=[], schema_entropy=schema_entropy,
            entity_entropy=entity_entropy, llm_rationale="smoke: AD unparsed, forcing Dis")

    # ── Dis round-trip (raw text vs parsed committed_pattern) ─────────────────────────
    emit(f"========== Dis call on [{focus.question_id}] ==========")
    dis_prompt = build_disambiguator_prompt(focus.question, ad_result, fm, empty_el, [])
    dis_raw = llm.generate_chat(
        [{"role": "system", "content": DIS_SYSTEM_PROMPT_V3},
         {"role": "user", "content": dis_prompt}],
        GenerationConfig(max_new_tokens=256, do_sample=False))[0].text
    dis_obj = _dis_extract_json(dis_raw)
    committed_pattern = (dis_obj or {}).get("committed_pattern")
    emit(f"  raw:    {dis_raw.strip()[:400]}")
    emit(f"  parsed committed_pattern: {committed_pattern!r}")
    emit()

    # ── QG round-trips: committed-pattern (C2/C3) and zero-shot (C1) ──────────────────
    # prompt_style="instruct": this script is API-only, so QG always gets the 8.3-follow-up
    # fix (include_properties=True + build_qg_prompt_api few-shots), matching how
    # build_condition2/3 construct it for a `kind: api` registry entry.
    qg = QueryGenerator(llm, prompt_style="instruct")
    committed_syntax = committed_pattern if isinstance(committed_pattern, str) else ""
    for label, syntax in (("committed-pattern", committed_syntax), ("zero-shot", "")):
        emit(f"========== QG call ({label}) on [{focus.question_id}] ==========")
        sm = SchemaMapping(question=focus.question, committed={},
                           cypher_syntax=syntax, resolution_mode="automated")
        qg_prompt = build_qg_prompt_api(
            focus.question, schema.to_prompt_string(include_properties=True),
            committed_pattern=(syntax or None))
        qg_raw = llm.generate(qg_prompt, qg._config)[0].text
        emit(f"  committed_pattern in: {syntax!r}")
        emit(f"  raw:     {qg_raw.strip()[:400]}")
        emit(f"  cleaned: {_clean_cypher(qg_raw)[:400]}")
        emit()

    report = out.getvalue()
    print(report)
    path = args.report or f"results/api_smoke_{args.model_key}_v3.txt"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\nReport written -> {path}")


if __name__ == "__main__":
    main()
