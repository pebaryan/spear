# SPEAR Conference Demo Roadmap

## Goal
Deliver a credible 10-12 minute semantic web conference demo that shows:
- BPMN execution as RDF-backed state.
- SPARQL-based runtime introspection.
- Query-backed evidence for process behavior and troubleshooting.

## Demo Narrative (Target)
1. Load a BPMN workflow with a realistic decision point.
2. Start a process instance with input variables.
3. Execute one service-task path and one exception/escalation path.
4. Run SPARQL queries to explain:
   - why a branch was taken,
   - where a stalled token is waiting,
   - what audit trail exists for a specific instance.
5. Close with limitations and next research steps.

## Feature Readiness Matrix
1. `BPMN deploy + execution API`: Ready (existing API and tests).
2. `RDF persistence across definitions/instances/tasks/audit`: Ready.
3. `Topic handlers (HTTP + builtin function path)`: Ready for demo.
4. `Security baseline (API keys, rate limit, outbound guardrails)`: Ready.
5. `Conference query pack with expected outputs`: Ready (`examples/conference_demo/queries/` + generated output artifacts).
6. `PROV-O mapping profile and SHACL validation demo`: Draft ready (`examples/conference_demo/semantic/`).
7. `Live dashboard/visualization for query results`: Optional, not ready.

## Milestones
### T-3 Weeks
1. Freeze one primary scenario and one fallback scenario.
2. Prepare canonical dataset and deterministic input payloads.
3. Define expected outputs for each key API call and SPARQL query.

### T-2 Weeks
1. Implement query pack in a `queries/` folder:
   - `trace_instances.sparql`
   - `why_branch_taken.sparql`
   - `find_waiting_tokens.sparql`
   - `audit_summary.sparql`
2. Add one script to run all queries and print compact outputs.
3. Draft one slide with concrete query results from rehearsal data.

### T-1 Week
1. Run full end-to-end rehearsal 3-5 times.
2. Capture backup screencast of ideal run.
3. Validate offline fallback path (no internet assumptions).
4. Freeze demo branch and only allow blocker fixes.

### T-2 Days
1. Do one timing rehearsal with conference speaker notes.
2. Verify machine setup and local dependencies.
3. Validate all command snippets on a clean shell session.

## Backlog With Acceptance Criteria
1. `Query Pack`
Acceptance:
- Each query returns non-empty deterministic output on demo dataset.
- Output includes instance IDs and timestamps to support narrative.

2. `Provenance Mapping Note (PROV-O Draft)`
Acceptance:
- At least one slide and one markdown note mapping runtime events to PROV entities/activities/agents.
- Includes at least one concrete triple example.

3. `SHACL Sanity Validation`
Acceptance:
- One shape file validates core constraints (required status/type edges).
- Demo can show pass/fail on one valid and one intentionally broken instance.

4. `Demo Runner Scripts`
Acceptance:
- Graph-native runner (`demo_runner.py`) and API runner (`api_demo_runner.py`) both execute successfully.
- Each exits non-zero if expected checks fail.

5. `Failure Recovery Script`
Acceptance:
- If external HTTP handler fails, switch to local mock topic handler in under 30 seconds.

## Rehearsal Runbook
1. Run `python examples/conference_demo/demo_runner.py --reset`.
2. Confirm generated outputs in `examples/conference_demo/expected_outputs/`.
3. Verify two instances:
   - normal path,
   - exception/escalation path.
4. Run SHACL validation (optional): `python examples/conference_demo/semantic/validate_shapes.py`.
5. Run query pack and narrate results.
6. Show one limitation slide before Q&A.

## Conference Day Go/No-Go Checklist
1. Can process deployment and instance creation run locally?
2. Can all 4 demo queries return expected outputs?
3. Is backup screencast available locally?
4. Is fallback mock handler path verified?
5. Is the environment pinned (no surprise dependency updates)?

If any answer is no, switch to fallback flow and present recorded run with live Q&A on architecture and queries.

## Suggested Next Repo Artifacts
1. `examples/conference_demo/processes/` with frozen BPMN files.
2. `examples/conference_demo/queries/` with the query pack.
3. `examples/conference_demo/demo_runner.py` and `api_demo_runner.py` for scripted runs.
4. `examples/conference_demo/expected_outputs/` for deterministic checks.
