import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from rdflib import Literal, Namespace, RDF, URIRef, XSD

try:
    from litellm import completion
except Exception:  # pragma: no cover - optional dependency
    completion = None

AGT = Namespace("http://example.org/agent/")
MEM = Namespace("http://example.org/memory/")
SRC = Namespace("http://example.org/source/")
VAR = Namespace("http://example.org/variables/")

DEFAULT_BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def is_verbose() -> bool:
    return os.getenv("AGENT_VERBOSE", "").strip().lower() in {"1", "true", "yes", "on"}


def log(message: str) -> None:
    if is_verbose():
        print(f"[agent] {message}")


def get_agent_uri(graph, context) -> Optional[URIRef]:
    agent_uri = context.get_variable("agent_uri")
    if agent_uri:
        return URIRef(str(agent_uri))

    for agent, _, _ in graph.triples((None, RDF.type, AGT.AgentInstance)):
        return agent
    return None


def get_cadence_seconds(graph, agent_uri: URIRef) -> int:
    cadence = graph.value(agent_uri, AGT.cadenceSeconds)
    if cadence is None:
        env_cadence = os.getenv("AGENT_CADENCE_SECONDS")
        if env_cadence:
            try:
                return int(env_cadence)
            except Exception:
                return 1800
        return 1800
    try:
        return int(cadence.toPython())
    except Exception:
        return 1800


def brave_search(query: str, api_key: str, count: int = 5) -> List[Dict[str, str]]:
    log(f"Brave search query: {query}")
    headers = {
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    }
    params = {"q": query, "count": count}
    brave_api_url = os.getenv("BRAVE_API_URL", DEFAULT_BRAVE_API_URL)
    with httpx.Client(timeout=20.0) as client:
        response = client.get(brave_api_url, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()

    results = []
    for item in payload.get("web", {}).get("results", []):
        results.append(
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "snippet": item.get("description", ""),
            }
        )
    return results


def llm_summary(prompt: str) -> str:
    if completion is None:
        log("LiteLLM not available; returning truncated prompt.")
        return prompt[:800]

    model = os.getenv("LITELLM_MODEL", "llama.cpp")
    provider = os.getenv("LITELLM_PROVIDER")
    api_key = os.getenv("LITELLM_API_KEY")
    api_base = os.getenv("LITELLM_API_BASE")
    if provider and "/" not in model:
        model = f"{provider}/{model}"
    log(f"LLM summary request via {model} (api_base={api_base})")
    response = completion(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Summarize the key findings for agent self-improvement.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        api_base=api_base,
        api_key=api_key,
    )
    return response["choices"][0]["message"]["content"].strip()


def strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    return cleaned


def normalize_goal(text: str) -> str:
    cleaned = " ".join(str(text).split())
    cleaned = cleaned.replace("your self", "yourself")
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    if cleaned and cleaned[-1] not in {".", "!", "?"}:
        cleaned = f"{cleaned}."
    return cleaned
