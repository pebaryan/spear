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

### View LLM Interactions

```bash
python agent.py interactions
```

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
│   └── agent_build.bpmn
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
| `bash` | Execute shell command |

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

### Web Search Not Working
```bash
# Get Brave API key from https://api.search.brave.com/
# Add to .env: BRAVE_API_KEY=your-key
```

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
