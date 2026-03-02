"""Natural language intent parser for the interactive agent."""

import json
import os
from typing import Dict, Optional, Tuple

try:
    from litellm import completion
except Exception:
    completion = None


INTENT_EXAMPLES = """
Examples of user inputs and their intents:
- "fix the failing tests" -> {"intent": "solve", "task": "Fix the failing tests in target_project/app.py"}
- "build a calculator" -> {"intent": "build", "task": "Create a calculator with add/sub/mul/div"}
- "fix this" or "make it work" -> {"intent": "auto", "task": "fix this"}  
- "keep trying until it works" -> {"intent": "auto", "task": "make this work"}
- "run autonomously" -> {"intent": "auto", "task": "fix the code"}
- "reset to the buggy state" -> {"intent": "reset"}
- "run the tests" -> {"intent": "tests"}
- "show me the code" -> {"intent": "cat"}
- "what have we done?" -> {"intent": "history"}
- "search for how to fix import errors" -> {"intent": "search", "query": "how to fix import errors in python"}
- "what skills do you have?" -> {"intent": "skills", "action": "list"}
- "search skills for debugging" -> {"intent": "skills", "action": "search", "query": "debugging"}
- "show my notes" -> {"intent": "scratch", "action": "list"}
- "remember that I tried option A" -> {"intent": "scratch", "action": "write", "content": "I tried option A"}
- "why did you make that decision?" -> {"intent": "explain", "type": "why"}
- "explain what happened" -> {"intent": "explain", "type": "last"}
- "show me the LLM calls" -> {"intent": "interactions"}
- "break down this task: build a web API" -> {"intent": "decompose", "task": "build a web API"}
- "list available tools" -> {"intent": "tools", "action": "list"}
- "quit" -> {"intent": "quit"}
- "exit" -> {"intent": "quit"}
- "help" -> {"intent": "help"}
"""


def parse_intent(user_input: str) -> Dict:
    """Parse natural language input into structured intent."""
    quick = _fallback_parse(user_input, strict=True)
    if quick.get("intent") != "unknown":
        return quick

    if completion is None:
        return _fallback_parse(user_input)

    model = os.getenv("LITELLM_MODEL", "gpt-4o")
    provider = os.getenv("LITELLM_PROVIDER")
    api_key = os.getenv("LITELLM_API_KEY")
    api_base = os.getenv("LITELLM_API_BASE")

    if provider and "/" not in model:
        model = f"{provider}/{model}"

    prompt = f"""You are an intent parser for a coding agent CLI. 
Given user input, identify what they want to do.

Available intents:
- solve: Fix bugs in target_project (single attempt)
- build: Build new code from scratch (single attempt)
- auto: Autonomous mode - keeps trying until success or max iterations
- reset: Reset target to buggy state
- tests: Run tests
- cat: Show current code
- history: Show session history
- search: Web search
- skills: List/import/search skills
- tools: List/available MCP tools
- scratch: Notes (list/write/search/summary)
- explain: Explain decisions (last/why/what-if/reflect/failure)
- interactions: Show LLM interactions
- decompose: Break down complex task
- help: Show available commands
- quit: Exit

For vague requests like "fix this", "make it work", "keep trying", use "auto" intent.

{INTENT_EXAMPLES}

User input: {user_input}

Respond with JSON only (no explanation):
{{
  "intent": "intent_name",
  "task": "task description (if applicable)",
  "action": "action (for skills/tools/scratch)",
  "query": "search query (if applicable)",
  "type": "type (for explain)"
}}
"""

    try:
        response = completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            api_base=api_base,
            api_key=api_key,
        )
        content = response["choices"][0]["message"]["content"].strip()

        # Extract JSON from response
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        parsed = json.loads(content.strip())
        if not isinstance(parsed, dict):
            return _fallback_parse(user_input)
        return parsed
    except Exception as e:
        print(f"[Intent parse error: {e}]")
        return _fallback_parse(user_input)


def _fallback_parse(user_input: str, strict: bool = False) -> Dict:
    """Simple rule-based fallback if LLM unavailable."""
    input_lower = user_input.lower().strip()
    if not input_lower:
        return {"intent": "help"}

    if input_lower in {"quit", "exit", "bye"}:
        return {"intent": "quit"}
    if input_lower in {"help", "commands"}:
        return {"intent": "help"}
    if input_lower in {"history", "what have we done"}:
        return {"intent": "history"}
    if input_lower in {"tests", "test", "run tests", "pytest"}:
        return {"intent": "tests"}
    if input_lower in {"cat", "show code", "show file"}:
        return {"intent": "cat"}
    if "llm calls" in input_lower or input_lower == "interactions":
        return {"intent": "interactions"}
    if input_lower.startswith("reset") or "buggy state" in input_lower:
        return {"intent": "reset"}

    if input_lower.startswith("search skills"):
        query = user_input[len("search skills") :].strip(" :")
        if query.startswith("for "):
            query = query[4:].strip()
        return {"intent": "skills", "action": "search", "query": query}
    if "skills" in input_lower and any(
        token in input_lower for token in ["what", "list", "have", "show"]
    ):
        return {"intent": "skills", "action": "list"}

    if input_lower.startswith("search for "):
        return {"intent": "search", "query": user_input[11:].strip()}
    if input_lower.startswith("search "):
        return {"intent": "search", "query": user_input[7:].strip()}
    if "look up" in input_lower or input_lower.startswith("google "):
        query = user_input.replace("look up", "", 1).replace("google", "", 1).strip()
        return {"intent": "search", "query": query}

    if input_lower.startswith("remember "):
        return {"intent": "scratch", "action": "write", "content": user_input[9:].strip()}
    if "note" in input_lower or "scratchpad" in input_lower or "memory" in input_lower:
        if input_lower.startswith("search notes "):
            return {
                "intent": "scratch",
                "action": "search",
                "query": user_input[13:].strip(),
            }
        return {"intent": "scratch", "action": "list"}

    if input_lower.startswith("explain "):
        tail = input_lower[8:].strip()
        if tail in {"why", "what-if", "reflect", "failure", "last"}:
            return {"intent": "explain", "type": tail}
        return {"intent": "explain", "type": "last"}
    if "why did" in input_lower or input_lower == "why":
        return {"intent": "explain", "type": "why"}

    if input_lower.startswith("decompose"):
        task = user_input[len("decompose") :].strip(" :")
        return {"intent": "decompose", "task": task}
    if "break down" in input_lower:
        task = user_input.lower().split("break down", 1)[1].strip(" :")
        return {"intent": "decompose", "task": task}

    auto_markers = [
        "make it work",
        "make this work",
        "fix this",
        "keep trying",
        "until it works",
        "autonomous",
        "run autonomously",
    ]
    if any(marker in input_lower for marker in auto_markers):
        return {"intent": "auto", "task": user_input.strip()}

    if input_lower.startswith("build ") or input_lower.startswith("create "):
        task = user_input.split(" ", 1)[1].strip()
        return {"intent": "build", "task": task}
    if input_lower.startswith("solve ") or input_lower.startswith("fix "):
        task = user_input.split(" ", 1)[1].strip()
        return {"intent": "solve", "task": task}
    if "debug" in input_lower or "bug" in input_lower:
        return {"intent": "solve", "task": user_input.strip()}

    if strict:
        return {"intent": "unknown"}
    return {"intent": "help"}


def format_help() -> str:
    """Format help message for user."""
    return """
Available commands (or just tell me what you want!):

BUILD & FIX:
   - "build a calculator" or "create a function that does X"
   - "fix the failing tests" or "debug this code"

AUTONOMOUS:
   - "fix this" or "make it work" 
   - "keep trying until it works"
   - Runs iteratively until success or max iterations

TOOLS:
   - "run the tests" or "tests"
   - "show me the code" or "cat"
   - "reset to buggy state"

KNOWLEDGE:
   - "what skills do you have?" / "search skills for X"
   - "show available tools"

MEMORY:
   - "show my notes" / "remember that X" / "search notes for X"

SEARCH:
   - "search for how to fix X"

ANALYSIS:
   - "show history" / "what did we do?"
   - "explain what happened" / "why did you do that?"
   - "show LLM interactions"

OTHER:
   - "decompose: build a web API"
   - "help"
   - "quit"

Just type naturally - I'll understand.
"""


def execute_intent(intent_data: Dict, agent_module) -> Tuple[bool, str]:
    """Execute the parsed intent."""
    intent = intent_data.get("intent", "help")
    task = intent_data.get("task", "")
    action = intent_data.get("action", "")
    query = intent_data.get("query", "")
    content = intent_data.get("content", "")
    explain_type = intent_data.get("type", "")
    nl_query = intent_data.get("nl_query", "")

    # Autonomous mode for vague requests
    if intent == "auto":
        if not task:
            task = "fix this"
        return True, f"auto {task}"

    # Handle natural language queries for certain intents
    if intent == "search" and nl_query:
        query = nl_query

    try:
        if intent == "build":
            if not task:
                return False, "What would you like me to build?"
            return True, f"build {task}"

        elif intent == "solve":
            solve_task = task or "Fix the failing tests in target_project/app.py"
            return True, f"solve {solve_task}"

        elif intent == "reset":
            return True, "reset"

        elif intent == "tests":
            return True, "tests"

        elif intent == "cat":
            return True, "cat"

        elif intent == "history":
            return True, "history"

        elif intent == "search":
            if not query and not nl_query:
                return False, "What would you like me to search for?"
            search_query = query or nl_query
            return True, f"search {search_query}"

        elif intent == "skills":
            if action == "search":
                if not query and not nl_query:
                    return False, "What would you like me to search skills for?"
                return True, f"skills search {query or nl_query}"
            return True, "skills list"

        elif intent == "tools":
            return True, "tools list"

        elif intent == "scratch":
            if action == "write":
                payload = content or query or nl_query
                if not payload:
                    return False, "What would you like me to remember?"
                return True, f"scratch write {payload}"
            elif action == "search":
                if not query and not nl_query:
                    return False, "What should I search for in notes?"
                return True, f"scratch search {query or nl_query}"
            elif action == "summary":
                return True, "scratch summary"
            return True, "scratch list"

        elif intent == "explain":
            exp_type = explain_type or action or "last"
            return True, f"explain {exp_type}"

        elif intent == "interactions":
            return True, "interactions"

        elif intent == "decompose":
            if not task:
                return False, "What task would you like me to break down?"
            return True, f"decompose {task}"

        elif intent == "help":
            return True, "help"

        elif intent == "quit":
            return True, "quit"

        else:
            return (
                False,
                f"I didn't understand that. Type 'help' for available commands.",
            )

    except Exception as e:
        return False, f"Error: {str(e)}"
