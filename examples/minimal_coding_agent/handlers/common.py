"""Shared utilities for the SPEAR minimal coding agent example."""

import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    logger.debug("python-dotenv not installed")
except Exception as e:
    logger.warning(f"Failed to load .env: {e}")


BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = BASE_DIR / "target_project"
APP_FILE = TARGET_DIR / "app.py"
REPORT_FILE = BASE_DIR / "latest_run_report.json"


try:
    from .llm_provenance import log_build_interaction, log_fix_interaction
except Exception:
    log_build_interaction = None
    log_fix_interaction = None

try:
    from .artifact_tracker import log_file_created, log_file_modified
except Exception:
    log_file_created = None
    log_file_modified = None

try:
    from .reasoning_trace import (
        log_approach_choice,
        log_fix_strategy,
        log_self_correction,
    )
except Exception:
    log_approach_choice = None
    log_fix_strategy = None
    log_self_correction = None

try:
    from .scratchpad import Scratchpad
except Exception:
    Scratchpad = None


BUGGY_APP_SOURCE = '''"""Tiny target module with an intentional bug for demo purposes."""


def running_average(total, count):
    """Return average value for total/count.

    Bug intentionally present:
    - Uses (count + 1), which is mathematically wrong.
    - Does not raise ValueError when count == 0.
    """
    if count < 0:
        raise ValueError("count cannot be negative")
    return total / (count + 1)
'''


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str


def literal_to_text(value) -> str:
    if value is None:
        return ""
    return str(value)


def literal_to_bool(value) -> bool:
    if value is None:
        return False
    try:
        parsed = value.toPython()
    except Exception:
        parsed = value
    if isinstance(parsed, bool):
        return parsed
    return str(parsed).strip().lower() in {"1", "true", "yes", "on"}


def literal_to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        parsed = value.toPython()
    except Exception:
        parsed = value
    try:
        return int(parsed)
    except Exception:
        return default


class WebSearchTool:
    """HTTP search tool with provider fallback."""

    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, max_results: int = 5) -> List[SearchResult]:
        for candidate in self._query_candidates(query):
            results = self._duckduckgo_search(candidate, max_results)
            if results:
                return results

            results = self._stack_overflow_search(candidate, max_results)
            if results:
                return results

            results = self._wikipedia_search(candidate, max_results)
            if results:
                return results
        return []

    @staticmethod
    def _simplify_query(query: str) -> str:
        tokens = re.findall(r"[A-Za-z0-9_]+", query.lower())
        keep = [token for token in tokens if len(token) > 2]
        return " ".join(keep[:8]) if keep else query

    def _query_candidates(self, query: str) -> List[str]:
        tokens = re.findall(r"[A-Za-z0-9_]+", query.lower())
        simplified = self._simplify_query(query)

        candidates = [query, simplified]

        focused = [
            token
            for token in tokens
            if token
            in {
                "python",
                "pytest",
                "valueerror",
                "zerodivisionerror",
                "division",
                "zero",
                "error",
                "failing",
                "test",
                "tests",
            }
        ]
        if focused:
            candidates.append(" ".join(focused[:5]))

        if "zero" in tokens and "division" in tokens:
            candidates.append("python zero division")
        if "pytest" in tokens:
            candidates.append("pytest failing test valueerror")
        if tokens:
            candidates.append(" ".join(tokens[:4]))

        unique: List[str] = []
        for item in candidates:
            norm = item.strip()
            if norm and norm not in unique:
                unique.append(norm)
        return unique

    def _duckduckgo_search(self, query: str, max_results: int) -> List[SearchResult]:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
            "no_redirect": 1,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        collected: List[SearchResult] = []

        abstract_url = str(payload.get("AbstractURL") or "")
        abstract_text = str(payload.get("AbstractText") or "")
        heading = str(payload.get("Heading") or "DuckDuckGo Abstract")
        if abstract_url and abstract_text:
            collected.append(
                SearchResult(
                    title=heading,
                    url=abstract_url,
                    snippet=abstract_text,
                    source="duckduckgo",
                )
            )

        def walk_topics(items) -> None:
            for item in items:
                if isinstance(item, dict) and "Topics" in item:
                    walk_topics(item["Topics"])
                    continue
                if not isinstance(item, dict):
                    continue
                text = str(item.get("Text") or "")
                first_url = str(item.get("FirstURL") or "")
                if text and first_url:
                    collected.append(
                        SearchResult(
                            title=text.split(" - ")[0],
                            url=first_url,
                            snippet=text,
                            source="duckduckgo",
                        )
                    )

        walk_topics(payload.get("RelatedTopics", []))
        return collected[:max_results]

    def _stack_overflow_search(
        self, query: str, max_results: int
    ) -> List[SearchResult]:
        url = "https://api.stackexchange.com/2.3/search/advanced"
        params = {
            "order": "desc",
            "sort": "relevance",
            "q": query,
            "site": "stackoverflow",
            "pagesize": max_results,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        items = payload.get("items", [])
        results: List[SearchResult] = []
        for item in items:
            results.append(
                SearchResult(
                    title=str(item.get("title", "")),
                    url=str(item.get("link", "")),
                    snippet=str(item.get("tags", [])),
                    source="stackoverflow",
                )
            )
        return [item for item in results if item.url][:max_results]

    def _wikipedia_search(self, query: str, max_results: int) -> List[SearchResult]:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "opensearch",
            "search": query,
            "limit": max_results,
            "namespace": 0,
            "format": "json",
        }
        headers = {"User-Agent": "spear-minimal-coding-agent/1.0 (educational-demo)"}
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception:
            return []

        if not isinstance(payload, list) or len(payload) < 4:
            return []

        titles = payload[1]
        descriptions = payload[2]
        links = payload[3]
        results: List[SearchResult] = []
        for title, description, link in zip(titles, descriptions, links):
            results.append(
                SearchResult(
                    title=str(title),
                    url=str(link),
                    snippet=str(description),
                    source="wikipedia",
                )
            )
        return results[:max_results]


class PythonTestTool:
    """Run pytest via Python subprocess without shell-specific commands."""

    @staticmethod
    def run_tests(project_dir: Path) -> Dict[str, str]:
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            ".",
            "--maxfail=1",
            "--disable-warnings",
            "--cache-clear",
        ]
        proc = subprocess.run(
            command,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        return {"exit_code": str(proc.returncode), "output": combined}


def build_failure_summary(pytest_output: str) -> str:
    lines = [line.strip() for line in pytest_output.splitlines() if line.strip()]
    interesting: List[str] = []
    for line in lines:
        if (
            "FAILED" in line
            or "E   " in line
            or "AssertionError" in line
            or "ZeroDivisionError" in line
            or "ValueError" in line
        ):
            interesting.append(line)
    if interesting:
        return " | ".join(interesting[:4])
    return "Tests failed; inspect pytest output."


def build_search_query(task: str, failure_summary: str) -> str:
    short_failure = re.sub(r"\s+", " ", failure_summary)[:180]
    return f"Python pytest fix bug: {short_failure}. Task: {task}"


def serialize_search_results(results: List[SearchResult]) -> str:
    return json.dumps([asdict(item) for item in results], indent=2)


try:
    from litellm import completion
except Exception:
    completion = None


def llm_fix_code(
    source_code: str, error_message: str, test_output: str, test_code: str = ""
) -> str:
    if completion is None:
        raise RuntimeError("LiteLLM not available. Install with: pip install litellm")

    model = os.getenv("LITELLM_MODEL", "gpt-4o")
    provider = os.getenv("LITELLM_PROVIDER")
    api_key = os.getenv("LITELLM_API_KEY")
    api_base = os.getenv("LITELLM_API_BASE")

    if provider and "/" not in model:
        model = f"{provider}/{model}"

    if log_fix_strategy:
        try:
            log_fix_strategy(
                bug_description=error_message[:200],
                strategy="LLM-based code repair",
                rationale="Test failures detected, LLM can analyze error and generate fix",
                alternative_strategies=[
                    "AST mutation",
                    "Template replacement",
                    "Manual fix",
                ],
            )
        except Exception:
            pass

    prompt = f"""You are a Python code repair expert. Given the source code, error message, test output, and test cases, fix the bug.

Source code:
```python
{source_code}
```

Test code:
```python
{test_code}
```

Error message:
{error_message}

Test output:
{test_output}

Requirements from tests:
1. running_average(10, 2) should return 5
2. running_average(10, 0) should raise ValueError
3. running_average(10, -1) should raise ValueError

Respond with the fixed source code only. Do not include any explanation or markdown formatting. Just return the complete corrected Python file."""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        api_base=api_base,
        api_key=api_key,
    )
    content = response["choices"][0]["message"]["content"].strip()
    content = content.strip()
    if content.startswith("```python"):
        content = content[10:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]

    if log_fix_interaction:
        try:
            log_fix_interaction(
                source_code=source_code,
                error_message=error_message,
                prompt=prompt,
                response=content,
                model=model,
                success=False,
                metadata={"temperature": 0.2},
            )
        except Exception as e:
            logger.warning(f"Failed to log fix interaction: {e}")

    return content.strip()


def llm_build_code(task: str, project_dir: Path) -> dict:
    if completion is None:
        raise RuntimeError("LiteLLM not available. Install with: pip install litellm")

    model = os.getenv("LITELLM_MODEL", "gpt-4o")
    provider = os.getenv("LITELLM_PROVIDER")
    api_key = os.getenv("LITELLM_API_KEY")
    api_base = os.getenv("LITELLM_API_BASE")

    if provider and "/" not in model:
        model = f"{provider}/{model}"

    steps = []

    if log_approach_choice:
        try:
            log_approach_choice(
                task=task,
                chosen_approach="Generate code from scratch with LLM",
                rationale="Task requires creating new functionality, LLM can generate both implementation and tests",
                alternatives=[
                    "Use template",
                    "Copy existing code",
                    "Manual implementation",
                ],
            )
        except Exception:
            pass

    prompt = f"""You are a Python code generator. Given a task description, generate a complete Python project with:
1. A main app.py file with the implementation
2. A test_app.py file with basic tests

Task: {task}

Requirements:
- Create a complete, working implementation
- Include docstrings and type hints
- Write meaningful tests that verify the core functionality
- Keep it simple but functional

Respond with a JSON object in this format:
{{
  "app.py": "the complete source code for app.py",
  "test_app.py": "the complete test code"
}}

Do not include any explanation, just return the JSON."""

    response = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        api_base=api_base,
        api_key=api_key,
    )
    content = response["choices"][0]["message"]["content"].strip()

    try:
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        code_files = json.loads(content.strip())
        app_code = code_files.get("app.py", "")
        test_code = code_files.get("test_app.py", "")
    except json.JSONDecodeError:
        steps.append(
            {"stage": "parse_error", "error": "Failed to parse LLM response as JSON"}
        )
        return {"success": False, "output": content, "steps": steps, "exit_code": "1"}

    app_file = project_dir / "app.py"
    test_file = project_dir / "test_app.py"

    previous_app = None
    previous_test = None
    if app_file.exists():
        previous_app = app_file.read_text(encoding="utf-8")
    if test_file.exists():
        previous_test = test_file.read_text(encoding="utf-8")

    app_file.write_text(app_code, encoding="utf-8")
    test_file.write_text(test_code, encoding="utf-8")

    if log_file_created or log_file_modified:
        try:
            if previous_app:
                log_file_modified(str(app_file), app_code, previous_app, task=task)
            else:
                log_file_created(str(app_file), app_code, task=task)

            if previous_test:
                log_file_modified(str(test_file), test_code, previous_test, task=task)
            else:
                log_file_created(str(test_file), test_code, task=task)
        except Exception as e:
            logger.warning(f"Failed to log artifact change: {e}")

    steps.append({"stage": "files_written", "files": ["app.py", "test_app.py"]})

    test_result = PythonTestTool.run_tests(project_dir)
    exit_code = test_result["exit_code"]
    output = test_result["output"]

    steps.append({"stage": "tests_run", "exit_code": exit_code, "output": output[:500]})

    success = exit_code == "0"

    if not success:
        iteration = 0
        max_iterations = 3
        while iteration < max_iterations and exit_code != "0":
            iteration += 1
            steps.append({"stage": "iteration", "iteration": iteration})

            fix_prompt = f"""The tests failed. Fix the code to make tests pass.

Current app.py:
```python
{app_code}
```

Current test_app.py:
```python
{test_code}
```

Test output:
{output}

Respond with a JSON object with the fixed code:
{{
  "app.py": "fixed source code",
  "test_app.py": "fixed test code (if needed)"
}}"""

            response = completion(
                model=model,
                messages=[{"role": "user", "content": fix_prompt}],
                temperature=0.2,
                api_base=api_base,
                api_key=api_key,
            )
            content = response["choices"][0]["message"]["content"].strip()

            try:
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]

                code_files = json.loads(content.strip())
                app_code = code_files.get("app.py", app_code)
                test_code = code_files.get("test_app.py", test_code)

                previous_app = (
                    app_file.read_text(encoding="utf-8") if app_file.exists() else None
                )
                previous_test = (
                    test_file.read_text(encoding="utf-8")
                    if test_file.exists()
                    else None
                )

                app_file.write_text(app_code, encoding="utf-8")
                test_file.write_text(test_code, encoding="utf-8")

                if log_file_created or log_file_modified:
                    try:
                        if previous_app:
                            log_file_modified(
                                str(app_file),
                                app_code,
                                previous_app,
                                task=f"{task} (iteration {iteration})",
                            )
                        else:
                            log_file_created(
                                str(app_file),
                                app_code,
                                task=f"{task} (iteration {iteration})",
                            )

                        if previous_test:
                            log_file_modified(
                                str(test_file),
                                test_code,
                                previous_test,
                                task=f"{task} (iteration {iteration})",
                            )
                        else:
                            log_file_created(
                                str(test_file),
                                test_code,
                                task=f"{task} (iteration {iteration})",
                            )
                    except Exception as e:
                        logger.warning(f"Failed to log artifact change: {e}")

                test_result = PythonTestTool.run_tests(project_dir)
                exit_code = test_result["exit_code"]
                output = test_result["output"]

                steps.append(
                    {
                        "stage": f"iteration_{iteration}_result",
                        "exit_code": exit_code,
                        "output": output[:500],
                    }
                )

                if exit_code == "0":
                    success = True
                    break
            except Exception as e:
                steps.append(
                    {
                        "stage": "iteration_error",
                        "iteration": iteration,
                        "error": str(e),
                    }
                )

    if log_build_interaction:
        try:
            log_build_interaction(
                task=task,
                prompt=prompt,
                response=content[:5000] if "content" in locals() else "",
                model=model,
                success=success,
                metadata={"temperature": 0.5},
            )
        except Exception:
            pass

    return {
        "success": success,
        "output": output,
        "steps": steps,
        "exit_code": str(exit_code),
    }
