# AI Workflow Rules

> This file is the entry point for every implementation session. A kickoff prompt only
> needs to say: **"Implement step `<ID>`. Follow `/context/ai-workflow-rules.md`."**
> Rule 1 chains in everything else.

---

## 1. Start of every session (the reading chain — do this in order)

Before writing any code:

1. Read `/context/project-overview.md` in full — the *what* and *why*.
2. Read this file (`ai-workflow-rules.md`) in full.
3. Open `/context/progress-tracker.md`. Confirm the step you've been asked to implement is
   `not started` or `in progress`, and that **every step it `Depends on` is marked `done`**.
   If a dependency is not done, stop and report it — do not build on a missing contract.
4. Read the step's spec at `/context/feature-specs/<ID>-<slug>.md` **completely** before
   writing anything. The spec is bounded on purpose; everything you need for this step is
   in it or in its named dependencies.

---

## 2. While implementing

- **Implement only the current step.** Do not create, edit, or "improve" files outside
  the module(s) this step owns. If you find an earlier step is wrong or incomplete, stop
  and report it — do not silently fix it mid-step.
- **Never redefine shared types or contracts.** All dataclasses, `Literal`s, and shared
  signatures live in `pipeline/types.py` (step `0.1`). Import them; never re-declare them.
  If a type or contract seems unclear, the answer is in `0.1-types.md` — don't invent one.
- **Match the public signatures the spec declares verbatim.** Downstream steps were
  designed against them. Changing a signature silently breaks a later step in a future
  session.
- **Follow `/context/code-standards.md`** for Python version, typing, docstrings, imports,
  and tests. Do not introduce a hardcoded model name anywhere outside config.

---

## 3. When the spec doesn't resolve something

If you hit a genuine ambiguity the spec and its dependencies do not answer: **stop and
ask.** Do not silently pick an option. A blocked step recorded clearly is cheaper than a
wrong contract that propagates across sessions.

---

## 4. When you deviate from the spec

If you must do something different from what the spec says (a library doesn't behave as
described, an interface needs an extra parameter, etc.):

1. Make the smallest deviation that works.
2. Record it in `/context/decisions-log.md` as: **date · step · what the spec said · what
   you did · why.**
3. Note it in the step's `progress-tracker.md` row.

An undocumented deviation is the single most expensive thing for a future session to debug.

---

## 5. End of every session (completion handoff)

When the step is done:

1. Run (or describe, if it requires GPU/Neo4j and those aren't available) the step's
   **Acceptance criteria** from the spec. State which checks passed and which are deferred.
2. Update the step's row in `/context/progress-tracker.md`: set `Status`, fill in
   `Outputs` (the importable names/files produced) and a one-line `Handoff` note stating
   **what the next step can now import and rely on**.
3. End with a short summary: what was built, what it exposes, and what the next step
   expects from it.

---

## 6. Standing reminders

- Spec files are named `<ID>-<slug>.md` (e.g. `0.1-types.md`, `3.4-ambiguity-detector.md`)
  and live in `/context/feature-specs/`. There is no `spec-` prefix.
- The benchmark (`benchmark-updated.json`) is already canonical: `ambiguity_type ∈
  {schema, entity, intent, temporal, null}`. There is no migration/remapping step — do
  not write one.
- Model backends are swappable by config. Default base model is Mistral 7B, but it is an
  example default only; nothing may assume it.
- Entity Lookup and any validation/execution/evaluation step need a **live Neo4j** with
  the KG loaded. If the database isn't available, implement against the contract and mark
  validation deferred — do not stub the data.
