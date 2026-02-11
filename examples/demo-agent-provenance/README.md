# Demo: Semantic Provenance for Agentic Coding Actions (TAAPAAI 2026)

A minimal, headless demo that shows how a coding agent run can be captured as semantic provenance and queried for explanations (why/why-not/impact). It reuses the SPEAR mindset (BPMN/RDF provenance) but runs as a lightweight script for reproducibility.

## Contents
- `target_app/`: tiny Python app with a deliberate bug and tests.
- `agent_run.py`: simulates an agent run, applies a fix, and logs provenance as RDF.
- `demo-prov.ttl`: provenance graph emitted by the run (generated).
- `queries/`: SPARQL templates for explanations.
- `requirements.txt`: rdflib + pytest only.

## How it works
1. Run baseline tests (fail).
2. Attempt a policy-blocked shell command (e.g., `curl`); log a blocked action.
3. Apply a code fix (edit `target_app/app.py`, adjust failing test expectation).
4. Re-run tests (pass).
5. Emit provenance (`demo-prov.ttl`) with actions, statuses, targets, and reasons.

## Quick start
```bash
cd demo-agent-provenance
python agent_run.py
```

After the run:
- Provenance: `demo-prov.ttl`
- Test output printed to stdout

## Query examples
Use any SPARQL engine (e.g., `python -m rdflib.tools.rdfpipe` or a triplestore). Examples:
```bash
python - <<'PY'
from rdflib import Graph
from pathlib import Path
q = Path('queries/status.sparql').read_text()
g = Graph().parse('demo-prov.ttl')
for row in g.query(q):
    print(row)
PY
```

`queries/why-not-blocked.sparql` returns the blocked command explanation; `queries/why-change-file.sparql` shows why a file was edited.

## Ontology (minimal)
- Classes: `ag:Run`, `ag:Action`
- Properties: `ag:status`, `ag:tool`, `ag:reason`, `prov:used` (target artifact), `prov:wasAssociatedWith` (run), `prov:startedAtTime`.
- Namespaces: `ag: <http://example.org/agent#>`, `prov: <http://www.w3.org/ns/prov#>`

## Customizing
- Edit `POLICY` in `agent_run.py` to change blocked commands.
- Swap `target_app` with your own small repo (keep commands fast and deterministic).
- Extend SPARQL templates to include impact/what-if queries.

## Why this demo
- Fully headless (no browser/VR deps) and quick to run.
- Shows policy-aware "why-not" and successful "why" explanations over a reproducible trace.
- Designed to accompany a TAAPAAI 2026 workshop paper and ESWC poster/demo.
