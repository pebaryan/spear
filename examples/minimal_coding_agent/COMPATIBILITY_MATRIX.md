# Compatibility Matrix

Validated combinations for `examples/minimal_coding_agent`.

## Runtime Matrix

| Area | Supported | Validation Method |
|---|---|---|
| OS | Windows, Linux | CI workflow matrix (`windows-latest`, `ubuntu-latest`) |
| Python | 3.10, 3.11 | CI workflow matrix |
| Storage | Local Turtle RDF files (`*.ttl`) | Unit/integration tests |
| Retrieval Index | Local JSON cache (`.spear_context_index.json`) | Context retrieval tests |
| LLM Mode | Deterministic (LLM disabled), LLM-enabled | `eval_harness.py` deterministic + manual/env-enabled runs |
| Retry Policy | `standard`, `aggressive`, `conservative`, `auto` profiles | Retry policy + eval harness tests |
| Shell Tool | Platform-agnostic (`argv`, `powershell`, `cmd`, `sh`) | Tool regression tests |

## Configuration Compatibility

| Feature | Compatibility Notes |
|---|---|
| Shell enable flag | `SPEAR_ALLOW_SHELL_TOOL` preferred; `SPEAR_ALLOW_BASH_TOOL` kept for legacy |
| Approval policy | `SPEAR_APPROVAL_MIN_RISK` and per-action overrides supported |
| Approval actor | `--approval-user` and `SPEAR_APPROVAL_USER` |
| Redaction | `SPEAR_REDACTION_PROFILE=off|balanced|strict`, `SPEAR_REDACTION_EXTRA_KEYS` |
| External authz | `SPEAR_AUTHZ_PROVIDER=http` with `SPEAR_AUTHZ_URL` |
| Retry profile env | `SPEAR_RETRY_POLICY_PROFILE` (`standard|aggressive|conservative|auto`) |
| Release tags | `minimal-agent-vX.Y.Z` validated against changelog version headings |
| Git MCP tools | `git_status` and `git_diff` are read-only inspection helpers |

## Known Constraints

- Interactive approval prompts require TTY stdin.
- External authz integration currently supports HTTP provider only.
- OIDC login/session lifecycle is not yet integrated.
