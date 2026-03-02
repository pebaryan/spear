# Minimal Coding Agent Maturity Backlog

This backlog is structured as `P0/P1/P2` with objective outcomes and
acceptance criteria.

## P0 - Foundation (measure + stabilize)

### P0.1 Evaluation Harness
- Goal: Measure capability with repeatable runs.
- Scope:
  - Add `eval_harness.py` for scenario-based runs.
  - Capture per-run metrics: duration, exit codes, `run_id`, report outcome.
  - Emit JSON outputs under `evals/`.
- Acceptance criteria:
  - Can run deterministic baseline without external LLM.
  - Produces machine-readable summary with success rate and timing.

### P0.2 Deterministic Baseline Profile
- Goal: Keep a stable benchmark mode.
- Scope:
  - Ensure deterministic setting (`SPEAR_DISABLE_LLM_FIX=true`) is documented.
  - Provide one canonical baseline scenario (`reset -> tests -> solve -> tests`).
- Acceptance criteria:
  - Repeated baseline runs are executable from one command.

### P0.3 Regression Safety Net
- Goal: Prevent breakage while iterating.
- Scope:
  - Add tests for new evaluation helpers and reporting.
  - Keep existing minimal agent test suite green.
- Acceptance criteria:
  - `pytest examples/minimal_coding_agent/tests -q` passes.

## P1 - Capability Expansion

### P1.1 Structured Planner Loop
- Goal: Improve success on harder tasks.
- Scope:
  - Explicit plan/apply/verify loop with per-step outcomes.
  - Retry policy by failure class.
- Acceptance criteria:
  - Better pass rate on multi-step scenarios vs P0 baseline.

Progress update (2026-02-14):
- Done: explicit solve-time plan artifact with step-level statuses (`analyze/apply/verify/fallback`) is now captured and persisted in reports (`fix_plan`).
- Done: failure-class retry policy profiles now drive strategy selection (`standard|aggressive|conservative`) and can switch from LLM to deterministic fallback.
- Done: eval trend now captures `policy_profile` and reports policy-sliced success-rate rows for delta comparison.
- Done: `auto` policy profile now infers effective profile from historical run-report outcomes by failure class.
- Remaining: confidence/guardrail thresholds for auto-selection (minimum sample size + fallback hysteresis).

### P1.2 Smarter Edit Engine
- Goal: Reduce harmful rewrites.
- Scope:
  - AST-aware targeted edits and patch ranking.
  - Minimal-diff preference and rollback on regressions.
- Acceptance criteria:
  - Lower regression rate; smaller median patch size.

### P1.3 Repo Context Retrieval
- Goal: Improve file relevance and code understanding.
- Scope:
  - Symbol/dependency index and retrieval before LLM calls.
- Acceptance criteria:
  - Reduced irrelevant file edits on benchmark tasks.

Progress update (2026-02-14):
- Done: persistent context index cache (`.spear_context_index.json`) with incremental refresh for changed files.
- Done: dependency expansion now works from cached import metadata plus symbol-reference graph.
- Remaining: richer symbol/dependency ranking signals (ownership, recency, test-impact) and large-repo benchmark thresholds.

### P1.4 Tool Ecosystem Expansion
- Goal: Improve developer workflow coverage.
- Scope:
  - Add safe, composable workflow tools beyond file/test/search.
  - Expand git/repo inspection primitives used by planner and repair loops.
- Acceptance criteria:
  - Broader tool support with regression coverage and safe defaults.

Progress update (2026-02-14):
- Done: read-only git MCP tools added (`git_status`, `git_diff`) with workspace guardrails.
- Remaining: package-manager adapters, issue-tracker adapters, and PR/diff summarization tools.

## P2 - Production Hardening

### P2.1 Safety and Security Controls
- Goal: Safe default operations.
- Scope:
  - Command allowlists, path guardrails, secret redaction.
  - Prompt-injection resilience for imported skills/docs.
- Acceptance criteria:
  - Security-focused tests for shell/path/prompt edge cases.

Progress update (2026-02-14):
- Done: path guardrails for file tools.
- Done: shell tool gated behind explicit opt-in (`SPEAR_ALLOW_SHELL_TOOL`).
- Done: shell command allowlist + operator-chain blocking (safe-by-default).
- Done: prompt-injection sanitization for imported markdown skills with RDF safety flags.
- Done: secret redaction for reports, LLM/MCP logs, session history, artifacts, and explanations.
- Done: configurable redaction policy profiles per deployment (`off|balanced|strict`) with extra sensitive-key overrides.

### P2.2 Human-in-the-Loop UX
- Goal: Better operator control.
- Scope:
  - Approval gates for risky actions.
  - Better diff summaries and reasoning links per run.
- Acceptance criteria:
  - Clear pre/post-change visibility and actionable approvals.

Progress update (2026-02-14):
- Done: optional approval gates for medium/high risk MCP actions (`shell`, overwrite `write_file`).
- Done: per-run artifact summaries now capture file-level line deltas (+/-) for reports/explanations.
- Done: interactive CLI approve/deny flow for `tools call` (`--approval-mode`).
- Done: persisted approval audit trail (`approval_events.ttl`) with risk/decision metadata.
- Done: policy granularity via configurable min-risk thresholds (global and per action).
- Done: per-user attribution for approval events (`--approval-user` / `SPEAR_APPROVAL_USER`).
- Done: external authorization provider integration for approved risky actions (`SPEAR_AUTHZ_PROVIDER=http`).
- Remaining: deeper external identity federation (e.g., OIDC login/session lifecycle for interactive mode).

### P2.3 Release and Ops
- Goal: Predictable delivery lifecycle.
- Scope:
  - Versioned releases, changelog, compatibility matrix.
  - CI profile for benchmark and regression tracking.
- Acceptance criteria:
  - Reproducible release process with trend metrics.

Progress update (2026-02-14):
- Done: versioned changelog scaffold (`CHANGELOG.md`).
- Done: compatibility matrix documented (`COMPATIBILITY_MATRIX.md`).
- Done: deterministic CI profile runner (`ci_profile.py`) producing machine-readable and markdown outputs.
- Done: CI workflow matrix added (`.github/workflows/minimal-agent-ci.yml`) with eval artifact publishing.
- Done: release/ops playbook documented (`RELEASE.md`).
- Done: automated release tagging/publishing pipeline tied to changelog version entries (`release_pipeline.py` + `.github/workflows/minimal-agent-release.yml`).
- Remaining: signed release artifacts and SBOM/provenance attestation.
