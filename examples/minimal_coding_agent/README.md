# SPEAR Minimal Coding Agent (Platform Agnostic)

This example is a fully functional coding agent that runs as a BPMN process in
SPEAR (`RDFProcessEngine`), similar in structure to `examples/openclaw_clone`.
It uses Python-only execution for test running and file edits, plus live web
search over HTTP.

## Why this showcases SPEAR
1. Process logic is modeled in BPMN:
`processes/agent_fix_loop.bpmn`.
2. Execution is topic-based via SPEAR handlers:
`handlers/`.
3. Runtime and audit state is persisted as RDF:
`engine_graph.ttl`.

## Process flow
1. `maybe_reset_target`
2. `run_tests_before`
3. `summarize_failure`
4. `web_search`
5. `apply_fix`
6. `run_tests_after`
7. `write_report`

## Quick Start
From repo root:

```bash
python examples/minimal_coding_agent/agent.py solve --reset-target
```

Expected behavior:
1. Target project resets to buggy fixture.
2. Tests fail initially.
3. Agent searches web for debugging context.
4. Agent generates and validates repair candidates against tests.
5. Tests pass after patch.
6. JSON report written to `latest_run_report.json`.

## Repair strategy
1. Discover non-test Python source files in `target_project/`.
2. Generate AST-level mutation candidates (comparison/operator and off-by-one style changes).
3. Run pytest after each candidate and keep only improvements.
4. Accept a candidate only when tests pass.

## Search-only mode
```bash
python examples/minimal_coding_agent/agent.py search "python pytest ValueError zero division"
```

## Files
1. `agent.py`: SPEAR runner CLI.
2. `processes/agent_fix_loop.bpmn`: BPMN model.
3. `handlers/`: topic handler implementations.
4. `target_project/`: tiny buggy fixture app and tests.
