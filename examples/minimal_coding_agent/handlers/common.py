"""Shared utilities for the SPEAR minimal coding agent example."""

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

import httpx


BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DIR = BASE_DIR / "target_project"
APP_FILE = TARGET_DIR / "app.py"
REPORT_FILE = BASE_DIR / "latest_run_report.json"


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

    def _stack_overflow_search(self, query: str, max_results: int) -> List[SearchResult]:
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
