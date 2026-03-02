# Minimal Coding Agent 0.4.0

Release date: 2026-02-14

### Added
- Template knowledge graph storage and calibration pipeline.
- Approval gate system with policy thresholds and actor attribution.
- External HTTP authorization hook for approved risky actions.
- Redaction policy profiles (`off`, `balanced`, `strict`) and extra-key overrides.
- Deterministic CI profile runner (`ci_profile.py`) and CI workflow artifact publishing.

### Changed
- Shell execution model is platform-agnostic with safe-by-default allowlist controls.
- Explanations now include approval and authorization metadata.
