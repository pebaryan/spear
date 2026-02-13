# SPEAR Conference Demo Kit

This folder contains a deterministic demo scenario for semantic web conference
presentations.

## Contents
1. `processes/risk_routing_demo.bpmn`: frozen workflow used for demo.
2. `queries/*.sparql`: query pack for runtime explainability.
3. `demo_runner.py`: runs scenario and query pack end-to-end.
4. `semantic/prov_o_mapping.md`: draft PROV-O compatibility profile.
5. `semantic/core_shapes.ttl`: SHACL sanity checks for core runtime entities.
6. `semantic/validate_shapes.py`: optional SHACL validator (requires `pyshacl`).
7. `expected_outputs/`: generated run artifacts for rehearsal checks.

## Quick Start
```bash
python examples/conference_demo/demo_runner.py --reset
```

This command will:
1. Deploy the demo BPMN process.
2. Create one high-risk and one low-risk instance.
3. Produce one waiting user-task path and one auto-complete path.
4. Run the SPARQL query pack.
5. Save run artifacts to `examples/conference_demo/expected_outputs/`.

## API-Mode Runner
Run the same scenario through `/api/v1/*` endpoints:
```bash
python examples/conference_demo/api_demo_runner.py --mode inprocess --reset
```

Use a live server instead:
```bash
python examples/conference_demo/api_demo_runner.py --mode http --base-url http://127.0.0.1:8000
```

## One-Command Suite
```bash
./examples/conference_demo/demo_runner.sh
```

Skip SHACL in wrapper:
```bash
./examples/conference_demo/demo_runner.sh --skip-shacl
```

## Optional SHACL Validation
```bash
pip install pyshacl
python examples/conference_demo/semantic/validate_shapes.py
```

## Rehearsal Command Set
```bash
python examples/conference_demo/demo_runner.py --reset
python examples/conference_demo/api_demo_runner.py --mode inprocess --reset
python examples/conference_demo/semantic/validate_shapes.py
```

## Notes For Live Presentation
1. Use local data only (no external API dependency required).
2. Keep one backup screencast in case venue network/setup is unstable.
3. Show one limitation explicitly (see deck limitation slide).
