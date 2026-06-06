# Project: T2C Disambiguation Pipeline (Honours thesis)

This codebase is built ONE STEP AT A TIME from specs in `context/feature-specs/`.

## Before doing ANY implementation work
Read and follow `context/ai-workflow-rules.md` in full. It is the entry point and
chains you to `context/project-overview.md`, `context/progress-tracker.md`, and the
step's spec. Do not start coding until you have read the step's spec completely.

## Always-on guardrails (the rest live in the governance files — don't duplicate them here)
- Implement ONLY the step you were asked to. Do not modify files outside its scope.
- All shared types come from `pipeline/types.py` — import them, never redefine them.
- Never hardcode a model name outside config.
- Build in dependency order; don't start a step whose dependencies aren't `done` in the tracker.
- Record any deviation from a spec in `context/decisions-log.md`.
- If the spec leaves something genuinely ambiguous, STOP and ask — don't guess.

## Environment
- Python >=3.10 (3.11 recommended); pytest; declare new deps in pyproject.toml.
- Live Neo4j and a GPU are NOT needed until their phases (Neo4j at 3.2; GPU at 2.1).