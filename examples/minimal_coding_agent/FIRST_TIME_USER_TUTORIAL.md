# SPEAR Coding Agent - First-Time User Tutorial

Welcome to the SPEAR (Semantic Process Engine as RDF) coding agent! This tutorial will guide you from installation to your first successful run.

## Table of Contents

1. [What is SPEAR?](#what-is-spear)
2. [Quick Start (5 minutes)](#quick-start-5-minutes)
3. [First Build Task](#first-build-task)
4. [First Fix Task](#first-fix-task)
5. [Interactive Mode](#interactive-mode)
6. [Understanding Provenance](#understanding-provenance)
7. [Common Workflows](#common-workflows)
8. [Security & Safety](#security--safety)
9. [Next Steps](#next-steps)

---

## What is SPEAR?

SPEAR is a **coding agent powered by LLMs** with built-in RDF provenance tracking. Unlike standard AI coding assistants, SPEAR:

- **Tracks everything**: Every decision, tool call, and file change is recorded in RDF
- **Self-corrects**: Automatically repairs failed fixes using deterministic templates
- **Decomposes tasks**: Can split complex problems into sub-agent parallel execution
- **Uses skills**: Import domain-specific knowledge from markdown files
- **Safe by design**: Approval gates for risky operations, secret redaction

---

## Quick Start (5 minutes)

### Step 1: Navigate to the Agent

```bash
cd D:\code\spear\examples\minimal_coding_agent
```

### Step 2: Install Dependencies

```bash
pip install rdflib httpx python-dotenv litellm
```

### Step 3: Configure LLM

Create a `.env` file:

```bash
# Use minimax-m2.5-free via litellm
LITELLM_PROVIDER=anthropic
LITELLM_MODEL=minimax-m2.5-free
LITELLM_API_BASE=https://opencode.ai/zen
LITELLM_API_KEY=your-api-key
```

**Note**: If you don't have an API key, you can run in deterministic mode (see "Without LLM" section below).

### Step 4: Run Your First Command

```bash
python agent.py --help
```

You should see all available commands.

---

## First Build Task

Let's build a simple Python module from scratch.

### Task: Create a Calculator Module

```bash
python agent.py build "Create a Python module with add, subtract, multiply, and divide functions"
```

**What happens:**
1. Agent creates a structured plan
2. Generates code using LLM
3. Writes files to `target_project/`
4. Records all changes in RDF provenance files

**Check the results:**

```bash
ls target_project/
cat target_project/calculator.py
```

You should see:
```python
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

**View provenance:**

```bash
cat run_reports.ttl | head -50
```

This shows the RDF record of your build operation.

---

## First Fix Task

Now let's fix a buggy module.

### Step 1: Check the Target Project

```bash
cat target_project/app.py
```

You'll see a buggy Python module with intentional errors.

### Step 2: Run Tests to See Failures

```bash
python -m pytest target_project/test_app.py -v
```

You should see failing tests with error messages.

### Step 3: Ask the Agent to Fix

```bash
python agent.py solve --reset-target
```

**What happens:**
1. Agent reads test failures
2. Plans a fix strategy
3. Generates corrected code
4. Runs tests to verify fix
5. **Automatically retries** if tests still fail (using deterministic templates)

**Success indicators:**
- You'll see a `Run ID` in the output (e.g., `solve-20260308023815-bd8f6beb`)
- All tests should pass
- Provenance files will show the fix details

### Step 4: Verify the Fix

```bash
python -m pytest target_project/test_app.py -v
cat target_project/app.py
```

---

## Without LLM (Deterministic Mode)

If you don't have an LLM API key, you can still use the agent in deterministic mode:

```bash
# Windows
set SPEAR_DISABLE_LLM_FIX=true

# Unix/Linux/macOS
export SPEAR_DISABLE_LLM_FIX=true

# Then run
python agent.py solve --reset-target
```

The agent will use pre-defined repair templates instead of LLM generation.

---

## Interactive Mode

Interactive mode is perfect for learning and experimentation.

```bash
python agent.py interactive
```

You'll see a prompt: `> `

### Available Commands:

```
> build Create a function that reverses a string
> tests
> cat
> history
> solve --reset-target
> scratch write "I should try using a loop first"
> scratch list
> quit
```

### Example Session:

```
> build Create a function that checks if a string is a palindrome
Testing the generated code...

> tests
All tests passed!

> cat
def is_palindrome(s):
    s = s.lower().replace(" ", "")
    return s == s[::-1]

> history
Last 5 runs:
1. build - palindrome checker - success
2. tests - verification - success

> quit
```

---

## Understanding Provenance

SPEAR tracks everything in RDF. Here's how to explore it:

### Session History

```bash
python agent.py history
```

Shows all your runs with timestamps and success status.

### Run Reports

```bash
# View specific run report
python agent.py explain last

# Or query RDF directly
python -c "
from rdflib import Graph
g = Graph()
g.parse('run_reports.ttl', format='turtle')
for s, p, o in g:
    print(s, p, o)
"
```

### File Changes

```bash
python agent.py tools call git_diff
```

Shows what files were modified in your last run.

### Self-Explanation

```bash
# Why did I make this decision?
python agent.py explain why

# How did I do overall?
python agent.py explain reflect

# What would happen if I tried X?
python agent.py explain what-if
```

---

## Common Workflows

### Workflow 1: Bug Fixing Loop

```bash
# 1. Start with buggy state
python agent.py solve --reset-target

# 2. Check if fixed
python -m pytest target_project/test_app.py -v

# 3. If not fixed, run again (agent will auto-retry)
python agent.py solve

# 4. Verify
cat target_project/app.py
```

### Workflow 2: Build New Feature

```bash
# 1. Build from scratch
python agent.py build "Create a JSON validator module"

# 2. Review code
cat target_project/json_validator.py

# 3. Test it
python -m pytest target_project/ -v

# 4. Iterate if needed
python agent.py solve --reset-target
```

### Workflow 3: Task Decomposition

For complex tasks, decompose into sub-tasks:

```bash
python agent.py decompose "Build a REST API with authentication"
```

The agent will break this into:
- Setup project structure
- Create authentication module
- Build API endpoints
- Add database integration
- Write tests

### Workflow 4: Skills Integration

Import domain-specific knowledge:

```bash
# Create a skills file
cat > skills/my_patterns.md << 'EOF'
# Python Error Handling Patterns

Description: Best practices for error handling in Python.

## Examples

- Use specific exception types
- Log errors with context
- Clean up resources in finally blocks
EOF

# Import skills
python agent.py skills import skills/

# Ask agent to use skills
python agent.py build "Create a module with proper error handling using my patterns"
```

---

## Security & Safety

### Approval Gates

Enable approval for risky operations:

```bash
# Windows
set SPEAR_REQUIRE_APPROVALS=true
set SPEAR_APPROVAL_MIN_RISK=medium

# Unix/Linux/macOS
export SPEAR_REQUIRE_APPROVALS=true
export SPEAR_APPROVAL_MIN_RISK=medium
```

Now, shell commands and file overwrites will require your confirmation.

### Secret Redaction

Protect sensitive data in logs:

```bash
# Windows
set SPEAR_REDACTION_PROFILE=strict

# Unix/Linux/macOS
export SPEAR_REDACTION_PROFILE=strict
```

Options: `off`, `balanced`, `strict`

### Shell Tool Safety

The shell tool is **disabled by default**. Enable only in trusted environments:

```bash
# Windows
set SPEAR_ALLOW_SHELL_TOOL=true
set SPEAR_SHELL_ALLOWED_COMMANDS=python,pytest,git

# Unix/Linux/macOS
export SPEAR_ALLOW_SHELL_TOOL=true
export SPEAR_SHELL_ALLOWED_COMMANDS=python,pytest,git
```

**Warning**: Never enable shell tool in untrusted environments!

---

## Next Steps

### Explore Advanced Features

1. **Evaluation Harness**
   ```bash
   python eval_harness.py --deterministic --repeats 3
   ```

2. **Sub-Agent Parallel Execution**
   ```bash
   python agent.py decompose "Build a full-stack application"
   ```

3. **Custom Tools**
   ```python
   from handlers.mcp_tools import register_tool
   
   @register_tool(name="custom_tool", description="Does something")
   def custom_tool(args):
       return {"result": "success"}
   ```

4. **RDF Provenance Queries**
   ```python
   from handlers.session_history import query_history
   
   results = query_history("""
   PREFIX ag: <http://example.org/agent/>
   SELECT ?run ?task WHERE {
       ?run a ag:Run .
       ?run ag:task ?task .
   }
   """)
   ```

### Join the Community

- Read `MATURITY_BACKLOG.md` for roadmap
- Check `CHANGELOG.md` for updates
- Review `COMPATIBILITY_MATRIX.md` for compatibility info

### Best Practices

1. **Start small**: Begin with simple build/fix tasks
2. **Review changes**: Always check generated code before committing
3. **Use provenance**: Leverage RDF tracking to understand agent decisions
4. **Enable approvals**: For production work, enable approval gates
5. **Track sessions**: Use `history` to review your agent's work

---

## Troubleshooting

### LLM Not Available

```bash
set SPEAR_DISABLE_LLM_FIX=true
python agent.py solve --reset-target
```

### Web Search Not Working

Ensure outbound HTTPS access is available. The tool falls back between DuckDuckGo, StackOverflow, and Wikipedia.

### RDF Query Errors

```bash
# Check TTL files exist
ls *.ttl

# Validate RDF
python -c "from rdflib import Graph; g = Graph(); g.parse('session_history.ttl', format='turtle')"
```

### Permission Denied (Shell Tool)

```bash
# Windows
set SPEAR_ALLOW_SHELL_TOOL=true

# Unix/Linux/macOS
export SPEAR_ALLOW_SHELL_TOOL=true
```

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `python agent.py build <task>` | Build code from scratch |
| `python agent.py solve --reset-target` | Fix bugs in target project |
| `python agent.py auto <task>` | Autonomous mode with self-correction |
| `python agent.py interactive` | Interactive REPL mode |
| `python agent.py history` | View run history |
| `python agent.py explain last` | Explain last run |
| `python agent.py tools list` | List available tools |
| `python agent.py skills import <dir>` | Import skills from directory |
| `python agent.py scratch write <note>` | Write to scratchpad |
| `python eval_harness.py --deterministic` | Run evaluation harness |

---

## Your First Success Checklist

✅ Installed dependencies  
✅ Configured LLM (or set deterministic mode)  
✅ Ran `python agent.py build "simple task"`  
✅ Ran `python agent.py solve --reset-target`  
✅ Viewed provenance files (`*.ttl`)  
✅ Explored interactive mode  
✅ Understood security settings  

You're now ready to use SPEAR for real development tasks!

---

**Happy coding with SPEAR!** 🚀