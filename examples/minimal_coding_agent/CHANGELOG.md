# Changelog

All notable changes to the minimal coding agent are tracked here.

## [0.4.0] - 2026-02-14

### Added
- Template knowledge graph storage and calibration pipeline.
- Approval gate system with policy thresholds and actor attribution.
- External HTTP authorization hook for approved risky actions.
- Redaction policy profiles (`off`, `balanced`, `strict`) and extra-key overrides.
- Deterministic CI profile runner (`ci_profile.py`) and CI workflow artifact publishing.
- Structured solve planner loop metadata (`analyze/apply/verify/fallback`) in run reports.
- Retrieval index cache (`.spear_context_index.json`) with incremental updates.
- Safe git inspection MCP tools (`git_status`, `git_diff`).
- Retry policy profiles by failure class (`standard`, `aggressive`, `conservative`) with strategy-aware LLM/deterministic switching.
- Eval trend rows now include `policy_profile` with policy-sliced trend summaries.
- `auto` retry policy profile now infers effective profile from historical run-report outcomes by failure class.

### Changed
- Shell execution model is platform-agnostic with safe-by-default allowlist controls.
- Explanations now include approval and authorization metadata.

## [0.3.0] - 2026-02-14

### Added
- Evaluation harness with scenario metrics and trend CSV.
- Run ID correlation across reports, artifacts, and LLM provenance.
- Artifact line-delta summaries in reports/explanations.

## [0.2.0] - 2026-02-14

### Added
- Context retrieval and deterministic repair engine enhancements.
- Prompt-injection sanitization for imported skills.

## [0.1.0] - 2026-02-14

### Added
- Initial minimal coding agent demo with SPEAR BPMN/RDF orchestration.
