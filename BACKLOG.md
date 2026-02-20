# SPEAR Backlog

Last updated: 2026-02-19

## Conventions
- Status: `Open`, `In Progress`, `Blocked`, `Done`
- Priority: `P0`, `P1`, `P2`
- Owner: GitHub handle or `Unassigned`
- Target version: semantic version milestone (for example `v0.6.0`)

---

## BL-001 - Harden Timer Polling For Multi-Worker Deployments
- Status: `Open`
- Priority: `P0`
- Owner: `Unassigned`
- Target version: `TBD`

### Scope
- Add lease/lock semantics for claiming due timer jobs.
- Ensure `run_due_timers(...)` is safe under concurrent workers.

### Acceptance Criteria
- Given two API workers, each due timer job executes exactly once.
- Re-running due processing is idempotent (no duplicate side effects).
- Tests cover concurrent claim/execute/retry paths.

---

## BL-002 - Expand Event Subprocess Start Variant Support
- Status: `Open`
- Priority: `P0`
- Owner: `Unassigned`
- Target version: `TBD`

### Scope
- Add event subprocess start handling for `error`, `escalation`, `signal`, and `conditional`.
- Keep message/timer behavior backward-compatible.

### Acceptance Criteria
- Each start variant can trigger an event subprocess from BPMN definitions.
- Unsupported variants fail with explicit, auditable errors.
- Integration tests exist per variant with at least one happy path.

---

## BL-003 - Improve Interrupting vs Non-Interrupting Event Subprocess Semantics
- Status: `Open`
- Priority: `P0`
- Owner: `Unassigned`
- Target version: `TBD`

### Scope
- Model and enforce interrupting behavior against active parent scope tokens.
- Preserve non-interrupting concurrent execution behavior.

### Acceptance Criteria
- Interrupting start cancels or supersedes parent path per modeled scope rules.
- Non-interrupting start leaves parent execution active.
- Tests validate token state transitions for both modes.

---

## BL-004 - Extend Call Activity Binding Semantics
- Status: `Open`
- Priority: `P1`
- Owner: `Unassigned`
- Target version: `TBD`

### Scope
- Expand `calledElement` resolution/binding beyond current baseline behavior.
- Document fallback and error semantics when resolution fails.

### Acceptance Criteria
- Resolution strategy is deterministic and documented.
- Invalid or missing bindings return explicit runtime errors.
- Integration tests cover resolved, unresolved, and fallback scenarios.

---

## BL-005 - Deepen Call Activity Lifecycle Observability
- Status: `Open`
- Priority: `P1`
- Owner: `Unassigned`
- Target version: `TBD`

### Scope
- Enrich parent/child execution linkage and lifecycle events.
- Improve audit triples for call start, completion, failure, and mapping stats.

### Acceptance Criteria
- Parent execution can be traced to child execution and back.
- Lifecycle states are queryable for start/end/failure.
- Tests verify emitted RDF triples and status transitions.

---

## BL-006 - Complete BPMN Task Variant Coverage
- Status: `Open`
- Priority: `P1`
- Owner: `Unassigned`
- Target version: `TBD`

### Scope
- Extend runtime support for additional task types beyond current send/manual baseline.
- Add explicit unsupported-task diagnostics where implementation is pending.

### Acceptance Criteria
- Newly supported task types are categorized and executable end-to-end.
- Unsupported types fail with clear, actionable errors.
- Section 4 support matrix in `README.md` is updated with each addition.
