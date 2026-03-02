# Release and Ops Playbook

This playbook standardizes release validation for the minimal coding agent.

## 1. Run local quality gates

```bash
python -m pytest examples/minimal_coding_agent/tests -q
python examples/minimal_coding_agent/ci_profile.py --repeats 1
python examples/minimal_coding_agent/showcase_demo.py
```

Expected artifacts:
- `examples/minimal_coding_agent/evals/latest_eval.json`
- `examples/minimal_coding_agent/evals/latest_summary.md`
- `examples/minimal_coding_agent/evals/trend.csv`
- `examples/minimal_coding_agent/evals/ci_profile_latest.json`
- `examples/minimal_coding_agent/evals/ci_profile_latest.md`

## 2. Update release metadata

- Add an entry in `examples/minimal_coding_agent/CHANGELOG.md`.
- Confirm `examples/minimal_coding_agent/COMPATIBILITY_MATRIX.md` is still accurate.
- Ensure `examples/minimal_coding_agent/MATURITY_BACKLOG.md` reflects current state.

## 3. CI validation

GitHub workflow: `.github/workflows/minimal-agent-ci.yml`

It validates:
- Minimal agent test suite.
- Deterministic CI profile run.
- Upload of eval/trend artifacts per OS/Python matrix run.

## 4. Automated release publishing

GitHub workflow: `.github/workflows/minimal-agent-release.yml`

Trigger:
- Push a tag in the format `minimal-agent-vX.Y.Z`.

Behavior:
- Runs `release_pipeline.py` to validate tag-to-changelog version alignment.
- Generates:
  - `evals/release_notes_latest.md`
  - `evals/release_metadata_latest.json`
- Publishes a GitHub release whose body is sourced from changelog notes.

Manual dry run:

```bash
python release_pipeline.py --tag minimal-agent-v0.4.0
```

## 5. Versioning convention

- Use semantic versioning in changelog headings (`MAJOR.MINOR.PATCH`).
- Increase:
  - `MAJOR` for breaking CLI/behavior changes,
  - `MINOR` for new capabilities,
  - `PATCH` for bug fixes/docs/tests only.
