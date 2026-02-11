# SPEAR-modeled agent demo

Runs the demo coding scenario as a BPMN process executed by the SPEAR RDF engine.

## Steps
```bash
cd /mnt/vmware/home/peb/works/hacks/phd/demo-agent-provenance
python spear_agent/run_spear_demo.py
```

Prereqs: Python with `rdflib` and `pytest` available, and SPEAR source at `/mnt/vmware/home/peb/works/hacks/spear` (used via `sys.path`).

## What it does
- Loads `processes/agent_demo.bpmn` (Start → run_tests → blocked_cmd → apply_fix → run_tests → End).
- Handlers:
  - `run_tests`: executes `pytest` in `target_app/` and records exit code/output.
  - `blocked_cmd`: simulates a policy-blocked shell command.
  - `apply_fix`: patches the bug and test expectation in `target_app/app.py` and `tests.py`.
- RDFProcessEngine executes the process and writes provenance to `spear_agent/spear-demo-prov.ttl` and `engine_graph.ttl`.

## Files
- `processes/agent_demo.bpmn` — BPMN model with Camunda topics.
- `handlers/agent_handlers.py` — topic handlers.
- `run_spear_demo.py` — runner wiring BPMN→RDF→engine.
- `queries/` — SPARQL templates aligned with paper sections (`why.sparql`, `why-not.sparql`, `impact.sparql`).
- Output: `spear-demo-prov.ttl`, `engine_graph.ttl`, `memory_graph.ttl` (if created).

## Notes
- Uses the same `target_app` as the headless demo; quick, headless, deterministic.
- Extendable: add policies/variables or hook a triplestore instead of local Turtle.

## Running the paper queries
Run the demo, then execute all paper queries in one command:

```bash
cd /mnt/vmware/home/peb/works/hacks/phd/demo-agent-provenance
python spear_agent/run_spear_demo.py
python spear_agent/run_queries.py
```

`run_queries.py` auto-detects:
- latest run URI for `why.sparql` and `why-not.sparql`
- latest edit action URI for `impact.sparql`

```bash
python spear_agent/run_queries.py --run-uri "http://example.org/instance/..."
python spear_agent/run_queries.py --action-uri "http://example.org/agent/action/..."
```
