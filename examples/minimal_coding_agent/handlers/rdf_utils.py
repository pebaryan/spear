"""Shared RDF utilities for reducing code duplication.

This module provides common functions for creating, loading, and saving RDF graphs.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


def get_base_dir() -> Path:
    """Get the base directory for the agent."""
    return BASE_DIR


DEFAULT_NAMESPACES = {
    "ag": "http://example.org/agent/",
    "proc": "http://example.org/process/",
    "var": "http://example.org/variables/",
    "llm": "http://example.org/llm/",
    "art": "http://example.org/artifact/",
    "reason": "http://example.org/reasoning/",
    "mem": "http://example.org/memory/",
    "mcp": "http://example.org/mcp/",
    "skill": "http://example.org/skill/",
    "sub": "http://example.org/subtask/",
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}


def create_graph(namespaces: Optional[Dict[str, Any]] = None) -> Graph:
    """Create a new RDF graph with common namespaces."""
    g = Graph()

    ns = namespaces or DEFAULT_NAMESPACES
    for prefix, uri in ns.items():
        try:
            g.bind(prefix, uri)
        except Exception:
            pass

    return g


def load_graph(file_path: Path, namespaces: Optional[Dict[str, Any]] = None) -> Graph:
    """Load an RDF graph from a file."""
    g = create_graph(namespaces)

    if file_path.exists():
        try:
            g.parse(file_path, format="turtle")
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")

    return g


def save_graph(g: Graph, file_path: Path) -> bool:
    """Save an RDF graph to a file."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        g.serialize(file_path, format="turtle")
        return True
    except Exception as e:
        logger.error(f"Failed to save {file_path}: {e}")
        return False


def get_count(g: Graph, predicate: Any, obj: Any) -> int:
    """Count subjects matching a pattern."""
    return sum(1 for _ in g.subjects(predicate, obj))


def add_with_check(g: Graph, subject: Any, predicate: Any, obj: Any) -> None:
    """Add a triple only if it doesn't exist."""
    if (subject, predicate, None) not in g:
        g.add((subject, predicate, obj))


def safe_literal(value: Any, datatype: Any = None) -> Literal:
    """Create a literal with proper type handling."""
    if isinstance(value, bool):
        return Literal(value, datatype=XSD.boolean)
    elif isinstance(value, int):
        return Literal(value, datatype=XSD.integer)
    elif isinstance(value, float):
        return Literal(value, datatype=XSD.float)
    elif datatype:
        return Literal(str(value), datatype=datatype)
    else:
        return Literal(str(value))


def query_graph(g: Graph, sparql: str) -> List[Dict[str, str]]:
    """Execute a SPARQL query and return results as dicts."""
    results = []
    try:
        for row in g.query(sparql):
            result = {}
            for var in row.labels:
                result[var] = str(row[var]) if row[var] else None
            results.append(result)
    except Exception as e:
        logger.warning(f"SPARQL query failed: {e}")
    return results


class RDFModuleBase:
    """Base class for RDF modules with common functionality."""

    def __init__(self, file_path: Path, namespaces: Optional[Dict[str, Any]] = None):
        self.file_path = file_path
        self.namespaces = namespaces or DEFAULT_NAMESPACES

    def _create_graph(self) -> Graph:
        return create_graph(self.namespaces)

    def load(self) -> Graph:
        return load_graph(self.file_path, self.namespaces)

    def save(self, g: Graph) -> bool:
        return save_graph(g, self.file_path)

    def get_graph(self) -> Graph:
        """Get existing graph or create new one."""
        return self.load()

    def _get_count(self, predicate: Any, obj: Any) -> int:
        g = self.get_graph()
        return get_count(g, predicate, obj)
