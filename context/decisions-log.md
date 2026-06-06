# Decisions Log

A lightweight record of choices made **during implementation that deviate from the
spec** — a library behaving differently than described, an interface needing an extra
parameter, a contract that had to change. Not for pre-planned design decisions (those
live in `project-overview.md` §10) and not for routine status (that's `progress-tracker.md`).

When you pick up this project weeks later and ask "why is this the way it is?", the answer
should be here.

## How to add an entry

One row per deviation. Keep the *why* concrete.

| Date | Step | Spec said | What we did | Why |
|------|------|-----------|-------------|-----|
| | | | | |

---

### Example of a good entry (delete once real entries exist)

| Date | Step | Spec said | What we did | Why |
|------|------|-----------|-------------|-----|
| 2026-01-15 | 3.7 | `cyver_validator` returns `properties_score: float` | Allowed `None` when the query accesses no properties | CyVer's `PropertiesValidator.validate()` returns `None` (not a score) for property-free queries; forcing a float would misreport. Type already `Optional[float]` in 0.1, so no downstream change. |

_No real entries yet._
