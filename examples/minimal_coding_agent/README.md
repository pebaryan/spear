# SPEAR Minimal Coding Agent

A self-introspective, RDF-native coding agent powered by LLM with full provenance tracking, sub-agent dispatch, MCP tools, and skill management.

## Features

| Feature | Description |
|---------|-------------|
| **Code Generation** | Build code from scratch using LLM |
| **Bug Fixing** | Fix bugs using LLM with test feedback |
| **Sub-Agent Dispatch** | Decompose complex tasks and execute in parallel |
| **MCP Tools** | Extensible tool system with 5 built-in tools |
| **Skills** | Import markdown skills into RDF for agent use |
| **Provenance** | Full RDF tracking of all operations |
| **Run IDs** | Every run gets a unique ID for correlated reports/explanations |
| **Context Retrieval** | Ranks relevant project files/symbols for better prompting |
| **Context Index Cache** | Persistent file/symbol index (`.spear_context_index.json`) with incremental refresh for faster large-repo retrieval |
| **Dependency Expansion** | Pulls import- and symbol-related files into prompt context |
| **Structured Planner Loop** | Solve flow now records explicit `analyze/apply/verify/fallback` step outcomes per run |
| **Retry Policy Profiles** | Failure-class retry strategy (`standard`, `aggressive`, `conservative`, `auto`) controls LLM-vs-deterministic repair switching |
| **AST Patch Templates** | Deterministic repairs use template confidence + suspect-line prioritization |
| **Template Knowledge Graph** | Repair template definitions/weights are stored in RDF and updated by calibration |
| **Multi-File Repair** | Pairwise mutation search can apply coordinated edits across files |
| **Safety Controls** | Shell commands are allowlisted, skills are injection-sanitized, and secrets are redacted in logs |
| **Redaction Profiles** | Deployment-specific redaction behavior (`off`, `balanced`, `strict`) with custom sensitive key extensions |
| **Approval Gates** | Optional human approval for medium/high risk MCP actions (`shell`, overwrite `write_file`) |
| **External AuthZ** | Optional HTTP authorization check validates approved risky actions against external policy/identity providers |
| **Self-Explanation** | Generate why/what-if/reflection explanations |
| **Scratchpad** | Persistent working memory |
| **Interactive Mode** | REPL for interactive development |

## Installation

```bash
# Install dependencies
pip install rdflib httpx python-dotenv litellm

# Or install all
pip install -r requirements.txt
```

## Configuration

Create `.env` file in the agent directory:

```bash
# LLM Configuration (using minimax-m2.5-free via litellm)
LITELLM_PROVIDER=anthropic
LITELLM_MODEL=minimax-m2.5-free
LITELLM_API_BASE=https://opencode.ai/zen
LITELLM_API_KEY=your-api-key
```

## Commands

### Build Code from Scratch

```bash
python agent.py build "Create a function that calculates fibonacci numbers"
```

### Fix Bugs

```bash
python agent.py solve --reset-target
```

`solve`, `build`, and `auto` print a `Run ID` on completion.

### Autonomous Mode

```bash
python agent.py auto "make it work"
```

### Deterministic Showcase Run

```bash
# Runs reset -> failing tests -> solve -> passing tests -> explain
python showcase_demo.py
```

### Evaluation Harness (P0)

```bash
# Deterministic baseline evaluation
python eval_harness.py --deterministic --repeats 3

# Include LLM-dependent scenarios (build + auto)
python eval_harness.py --scenario solve_baseline --scenario build_baseline --scenario auto_baseline --repeats 2

# Compare retry policy profiles in trend outputs
python eval_harness.py --deterministic --scenario solve_baseline --policy-profile standard --repeats 2
python eval_harness.py --deterministic --scenario solve_baseline --policy-profile aggressive --repeats 2
python eval_harness.py --deterministic --scenario solve_baseline --policy-profile auto --repeats 2
```

Outputs:
- Per-run and aggregate metrics in `evals/eval_<timestamp>.json`
- Latest snapshot in `evals/latest_eval.json`
- CI trend rows in `evals/trend.csv`
- Markdown summary in `evals/latest_summary.md`
- Includes `run_id`, `policy_profile`, duration, exit codes, and success rate

Notes:
- `build_baseline` and `auto_baseline` are LLM-dependent.
- In `--deterministic` mode, LLM-dependent scenarios are marked as skipped.
- `--policy-profile auto` selects a profile from historical run-report outcomes by failure class.

### CI Profile (P2.3)

```bash
# Runs minimal test suite + deterministic baseline eval, then writes CI summary artifacts
python ci_profile.py --repeats 1
```

Outputs:
- `evals/ci_profile_latest.json`
- `evals/ci_profile_latest.md`

Template weight calibration:

```bash
# Recompute template weights from latest eval and write JSON + RDF KG
python calibrate_template_weights.py

# Optional outputs/flags
python calibrate_template_weights.py --eval-file evals/latest_eval.json --output template_weights.json --kg-output template_knowledge.ttl
python calibrate_template_weights.py --no-kg
```

### Decompose Tasks

```bash
python agent.py decompose "Build a web API with authentication and database"
```

### Interactive Mode

```bash
python agent.py interactive
```

Commands in interactive mode:
- `build <task>` - Build code
- `solve <task>` - Fix bugs
- `reset` - Reset target to buggy state
- `tests` - Run tests
- `cat` - Show current code
- `history` - View session history
- `quit` - Exit

### Web Search

```bash
python agent.py search "how to fix IndexError in Python"
```

### Explain Results

```bash
# Explain last run
python agent.py explain last

# Explain a specific run
python agent.py explain last --run-id solve-20260214062849-bd8f6beb

# Why did I make this decision?
python agent.py explain why

# Self-reflection
python agent.py explain reflect

# What-if analysis
python agent.py explain what-if

# LLM-powered explanation
python agent.py explain --query "Why did I succeed?"
```

### Session History

```bash
python agent.py history
```

`history` output now includes run IDs when available.

### View LLM Interactions

```bash
python agent.py interactions
```

`interactions` output includes run IDs, allowing you to correlate prompts/responses
with a single solve/build/auto run.

### MCP Tools

```bash
# List available tools
python agent.py tools list

# Call a tool
python agent.py tools call read_file '{"path":"app.py"}'
```

### Skills

```bash
# Import skills from directory
python agent.py skills import skills/

# List imported skills
python agent.py skills list

# Search skills
python agent.py skills search "bug"
```

### Scratchpad

```bash
# List notes
python agent.py scratch list

# Write a note
python agent.py scratch write "My thought"

# Search notes
python agent.py scratch search "keyword"

# View summary
python agent.py scratch summary
```

## Architecture

```
minimal_coding_agent/
├── agent.py                 # Main CLI entry point
├── handlers/                # Topic handlers for SPEAR
│   ├── common.py           # Shared utilities
│   ├── build_code.py      # Code generation
│   ├── apply_fix.py       # Bug fixing
│   ├── subagent.py        # Task decomposition
│   ├── complex_build.py   # Multi-agent build
│   ├── mcp_tools.py      # MCP tool system
│   ├── builtin_tools.py  # Built-in tools
│   ├── skill_import.py   # Markdown → RDF
│   ├── scratchpad.py     # Working memory
│   ├── reasoning_trace.py # Decision logging
│   ├── explanation_engine.py # NL explanations
│   ├── session_history.py   # Run history
│   ├── run_report.py       # Report generation
│   ├── llm_provenance.py   # LLM call tracking
│   └── artifact_tracker.py  # File change tracking
├── processes/              # BPMN definitions
│   ├── agent_fix_loop.bpmn
│   ├── agent_build.bpmn
│   └── autonomous_agent.bpmn
├── skills/                # Markdown skills
│   └── python_bug_fixes.md
└── target_project/       # Target code to fix/build
    ├── app.py
    └── test_app.py
```

## RDF Provenance

All operations are tracked in RDF:

| File | Description |
|------|-------------|
| `session_history.ttl` | Session run history |
| `run_reports.ttl` | Detailed run reports |
| `llm_interactions.ttl` | LLM prompts/responses |
| `artifact_changes.ttl` | File modifications |
| `reasoning_trace.ttl` | Decision reasoning |
| `scratchpad.ttl` | Working memory |
| `mcp_calls.ttl` | Tool invocations |
| `skills.ttl` | Imported skills |
| `template_knowledge.ttl` | Repair template definitions, weights, and calibration events |
| `approval_events.ttl` | Approval requests/decisions for risky actions |

Run correlation uses `ag:runId` (reports/history), `llm:runId` (LLM calls),
`art:runId` (artifact changes), and reasoning metadata (`reason:run_id`).
Run reports also include an `artifact_summary` with per-file line deltas when available.

Roadmap is tracked in `MATURITY_BACKLOG.md` with `P0/P1/P2` milestones.
Release/ops references:
- `CHANGELOG.md`
- `COMPATIBILITY_MATRIX.md`
- `RELEASE.md`

Tag-based release publishing:
- `.github/workflows/minimal-agent-release.yml` publishes on tags matching
  `minimal-agent-vX.Y.Z` and validates tag/changelog alignment via
  `release_pipeline.py`.

### SPARQL Queries

```python
from handlers.session_history import query_history
from handlers.run_report import query_reports

# Query failed runs
results = query_history("""
PREFIX ag: <http://example.org/agent/>
SELECT ?run ?task WHERE {
    ?run a ag:Run .
    ?run ag:success false .
    ?run ag:task ?task .
}
""")
```

## MCP Tools

Built-in tools:

| Tool | Description |
|------|-------------|
| `run_tests` | Run pytest tests |
| `read_file` | Read file contents |
| `write_file` | Write to file |
| `web_search` | Search the web |
| `git_status` | Show repository status (`git status --short`) |
| `git_diff` | Show repository diff (optionally staged/file-scoped) |
| `shell` | Execute shell commands cross-platform (disabled by default; opt-in) |
| `bash` | Legacy alias for `shell` |

### Register Custom Tools

```python
from handlers.mcp_tools import register_tool

@register_tool(
    name="my_tool",
    description="Does something useful",
    input_schema={"type": "object", "properties": {"arg": {"type": "string"}}}
)
def my_tool(args):
    return {"result": f"Processed: {args.get('arg')}"}
```

## Skills

Create markdown skills in `skills/` directory:

```markdown
# Python Bug Fix Patterns

Description: Common bug patterns and how to fix them.

## Examples

- Division by zero: Add checks for zero
- IndexError: Check list bounds

## Patterns

1. `if divisor == 0: raise ValueError(...)`
2. `result = dict.get(key, default)`
```

Import and use:

```bash
python agent.py skills import skills/
python agent.py skills search "bug"
```

Security note:
- Imported skill text is sanitized against prompt-injection style instructions.
- Safety flags are stored in `skills.ttl`; `skills search` uses safe-only matching by default.
- Sensitive values (API keys/tokens/password-like fields) are redacted before report and provenance logging.

## Sub-Agents

The agent can decompose complex tasks:

```python
from handlers.subagent import decompose_task, run_parallel_subtasks

# Decompose into subtasks
subtasks = decompose_task("Build a full-stack app")
# Returns: [{"task": "setup", "description": "..."}, ...]

# Execute in parallel
results = run_parallel_subtasks(task_descriptions, executor_fn)
```

## Self-Explanation

The agent generates natural language explanations:

```python
from handlers.explanation_engine import (
    explain_last_run,
    explain_failure,
    generate_why_explanation,
    generate_what_if_scaffold,
    generate_reflection,
    llm_generate_explanation,
)

# Explain latest run
print(explain_last_run())

# Explain specific run
print(explain_last_run(run_id="solve-20260214062849-bd8f6beb"))

# Why did I make this decision?
print(generate_why_explanation())

# What would happen if...?
print(generate_what_if_scaffold())

# How did I do overall?
print(generate_reflection())

# Ask the agent anything
print(llm_generate_explanation("Why did I succeed?"))
```

## Testing

```bash
# Run unit tests
python -m pytest examples/minimal_coding_agent/tests/ -v

# Run specific test
python -m pytest examples/minimal_coding_agent/tests/test_handlers.py::TestMCP -v
```

## Workflow Example

```bash
# 1. Start interactive mode
python agent.py interactive

# 2. In interactive mode:
> build Create a calculator with add/sub/mul/div
> tests
> cat
> history
> quit
```

## API Usage

```python
from handlers.common import llm_build_code, llm_fix_code
from handlers.scratchpad import Scratchpad
from handlers.subagent import decompose_task, dispatch_subagents
from handlers.mcp_tools import call_tool, register_tool

# Build code
result = llm_build_code("Create a hello world function", target_dir)

# Fix code
fixed = llm_fix_code(source_code, error_msg, test_output)

# Use scratchpad
scratchpad = Scratchpad()
scratchpad.think("I should try this approach...")
scratchpad.remember("Important insight", tags=["insight"])

# Decompose task
subtasks = decompose_task("Build an API")
```

## Troubleshooting

### LLM Not Available
```bash
pip install litellm
```

You can still run a deterministic repair flow without LLM:

```bash
set SPEAR_DISABLE_LLM_FIX=true
python agent.py solve --reset-target
```

### Web Search Not Working
```bash
# Web search uses DuckDuckGo, StackOverflow, and Wikipedia APIs.
# Ensure outbound HTTPS access is available from your environment.
# If your network blocks one source, the tool falls back to others.
```

### Shell Tool Disabled
```bash
# The shell MCP tool is disabled by default for safety.
# Enable explicitly only in trusted environments:
set SPEAR_ALLOW_SHELL_TOOL=true

# Enable approval gates for medium/high risk tool actions.
set SPEAR_REQUIRE_APPROVALS=true

# Global minimum risk level that requires approval: low|medium|high
set SPEAR_APPROVAL_MIN_RISK=medium

# Optional per-action overrides
set SPEAR_APPROVAL_MIN_RISK_SHELL=low
set SPEAR_APPROVAL_MIN_RISK_WRITE_FILE=medium

# Optional actor attribution for approval audit rows
set SPEAR_APPROVAL_USER=operator1

# Redaction policy profile for reports/provenance: off|balanced|strict
set SPEAR_REDACTION_PROFILE=balanced

# Optional extra sensitive object keys (comma separated)
set SPEAR_REDACTION_EXTRA_KEYS=private_note,internal_secret

# Optional external authorization provider for approved risky actions
set SPEAR_AUTHZ_PROVIDER=http
set SPEAR_AUTHZ_URL=https://authz.example.com/authorize
set SPEAR_AUTHZ_TOKEN=your-service-token
set SPEAR_AUTHZ_FAIL_MODE=deny
set SPEAR_AUTHZ_REQUIRE_ACTOR=true
set SPEAR_AUTHZ_TIMEOUT_SEC=3

# Retry policy profile for solve-loop strategy:
# standard | aggressive | conservative | auto
set SPEAR_RETRY_POLICY_PROFILE=auto

# Restrict allowed commands (comma or whitespace separated).
# Default allowlist includes safe read/test commands (python, pytest, git, ls, etc.).
set SPEAR_SHELL_ALLOWED_COMMANDS=python,pytest,git

# In trusted environments only, bypass command allowlist + operator checks:
set SPEAR_SHELL_ALLOW_UNSAFE=true

# Legacy env var is still accepted for compatibility:
set SPEAR_ALLOW_BASH_TOOL=true
```

Approval note:
- When `SPEAR_REQUIRE_APPROVALS=true`, risky `shell` and overwrite `write_file`
  actions return `approval_required=true` unless the tool call includes
  `"approved": true`.
- CLI `tools call` supports `--approval-mode prompt|auto|deny` (or env
  `SPEAR_APPROVAL_MODE`) to handle approval-required actions interactively.
- Optional actor attribution: `tools call ... --approval-user <id>` (or env
  `SPEAR_APPROVAL_USER`) for approval audit identity.
- If external authz is enabled (`SPEAR_AUTHZ_PROVIDER=http`), actions that
  include `"approved": true` are validated against the provider before
  execution. Provider metadata is persisted in `approval_events.ttl`.
- Approval requests and decisions are persisted in `approval_events.ttl`.

### RDF Query Errors
```bash
# Check TTL files exist
ls *.ttl

# Validate RDF
python -c "from rdflib import Graph; g = Graph(); g.parse('session_history.ttl', format='turtle')"
```

## Contributing

1. Add tests for new features
2. Follow PEP 8 style
3. Update documentation
4. Run tests before submitting

## License

MIT
