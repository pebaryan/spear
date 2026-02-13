"""Persistent scratchpad/memory for the coding agent.

This provides a working memory that persists across steps within a run,
allowing the agent to store intermediate thoughts, notes, and context.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
SCRATCHPAD_PATH = BASE_DIR / "scratchpad.ttl"
MEMORY_INDEX_PATH = BASE_DIR / "memory_index.json"

AG = Namespace("http://example.org/agent/")
MEM = Namespace("http://example.org/memory/")

_namespaces = {
    "ag": AG,
    "mem": MEM,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}


def _create_memory_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_memory_graph() -> Graph:
    g = _create_memory_graph()
    if SCRATCHPAD_PATH.exists():
        g.parse(SCRATCHPAD_PATH, format="turtle")
    return g


def save_memory_graph(g: Graph) -> None:
    g.serialize(SCRATCHPAD_PATH, format="turtle")


def _get_memory_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, MEM.Note):
        count += 1
    return count


def write_note(
    content: str, note_type: str = "thought", metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Write a note to the scratchpad."""
    g = load_memory_graph()

    note_id = _get_memory_count(g)
    note_uri = MEM[f"note/{note_id}"]

    g.add((note_uri, RDF.type, MEM.Note))
    g.add(
        (
            note_uri,
            MEM.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((note_uri, MEM.noteType, Literal(note_type)))
    g.add((note_uri, MEM.content, Literal(content)))

    if metadata:
        if "run_id" in metadata:
            g.add((note_uri, MEM.runId, Literal(metadata["run_id"])))
        if "step" in metadata:
            g.add((note_uri, MEM.step, Literal(metadata["step"])))
        if "tags" in metadata:
            for tag in metadata["tags"]:
                g.add((note_uri, MEM.tag, Literal(tag)))

    save_memory_graph(g)

    return str(note_uri)


def read_notes(
    limit: int = 50, note_type: str = None, tag: str = None
) -> List[Dict[str, Any]]:
    """Read notes from the scratchpad."""
    g = load_memory_graph()

    notes = []
    for note in g.subjects(RDF.type, MEM.Note):
        if note_type:
            note_type_val = g.value(note, MEM.noteType)
            if note_type_val and str(note_type_val) != note_type:
                continue

        if tag:
            has_tag = False
            for t in g.objects(note, MEM.tag):
                if str(t) == tag:
                    has_tag = True
                    break
            if not has_tag:
                continue

        data = {
            "uri": str(note),
            "timestamp": str(g.value(note, MEM.timestamp) or ""),
            "note_type": str(g.value(note, MEM.noteType) or ""),
            "content": str(g.value(note, MEM.content) or ""),
        }

        run_id = g.value(note, MEM.runId)
        if run_id:
            data["run_id"] = str(run_id)

        step = g.value(note, MEM.step)
        if step:
            data["step"] = str(step)

        tags = [str(t) for t in g.objects(note, MEM.tag)]
        if tags:
            data["tags"] = tags

        notes.append(data)

    notes.sort(key=lambda x: x["timestamp"], reverse=True)
    return notes[:limit]


def update_note(note_uri: str, content: str) -> bool:
    """Update an existing note."""
    g = load_memory_graph()

    note = URIRef(note_uri)
    if (note, RDF.type, MEM.Note) not in g:
        return False

    g.remove((note, MEM.content, None))
    g.add((note, MEM.content, Literal(content)))

    save_memory_graph(g)
    return True


def search_notes(query: str) -> List[Dict[str, Any]]:
    """Search notes by content."""
    g = load_memory_graph()

    notes = []
    query_lower = query.lower()

    for note in g.subjects(RDF.type, MEM.Note):
        content = g.value(note, MEM.content)
        if content and query_lower in str(content).lower():
            data = {
                "uri": str(note),
                "timestamp": str(g.value(note, MEM.timestamp) or ""),
                "note_type": str(g.value(note, MEM.noteType) or ""),
                "content": str(content),
            }
            notes.append(data)

    return notes


def get_recent_thoughts(limit: int = 10) -> List[str]:
    """Get recent thought contents as a simple list."""
    notes = read_notes(limit=limit, note_type="thought")
    return [n["content"] for n in notes]


def clear_memory() -> None:
    """Clear all memory."""
    g = _create_memory_graph()
    save_memory_graph(g)


def get_memory_summary() -> Dict[str, Any]:
    """Get a summary of the memory."""
    g = load_memory_graph()

    notes = list(g.subjects(RDF.type, MEM.Note))

    by_type = {}
    for note in notes:
        note_type = g.value(note, MEM.noteType)
        if note_type:
            t = str(note_type)
            by_type[t] = by_type.get(t, 0) + 1

    return {
        "total_notes": len(notes),
        "by_type": by_type,
    }


class Scratchpad:
    """Scratchpad context manager for a single run."""

    def __init__(self, run_id: str = None):
        self.run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.step = 0

    def think(self, thought: str, tags: List[str] = None) -> str:
        """Record a thought."""
        self.step += 1
        return write_note(
            thought,
            note_type="thought",
            metadata={"run_id": self.run_id, "step": self.step, "tags": tags or []},
        )

    def observe(self, observation: str, tags: List[str] = None) -> str:
        """Record an observation."""
        return write_note(
            observation,
            note_type="observation",
            metadata={"run_id": self.run_id, "step": self.step, "tags": tags or []},
        )

    def plan(self, plan: str, tags: List[str] = None) -> str:
        """Record a plan."""
        return write_note(
            plan,
            note_type="plan",
            metadata={"run_id": self.run_id, "step": self.step, "tags": tags or []},
        )

    def remember(self, info: str, tags: List[str] = None) -> str:
        """Remember something important."""
        return write_note(
            info,
            note_type="memory",
            metadata={"run_id": self.run_id, "tags": tags or ["important"]},
        )

    def recall(self, tag: str = None) -> List[str]:
        """Recall notes by tag."""
        notes = read_notes(note_type="memory", tag=tag)
        return [n["content"] for n in notes]

    def recent(self, limit: int = 5) -> List[str]:
        """Get recent thoughts."""
        return get_recent_thoughts(limit=limit)
