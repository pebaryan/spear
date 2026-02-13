"""RDF-based artifact tracker for file changes."""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
ARTIFACT_LOG_PATH = BASE_DIR / "artifact_changes.ttl"

AG = Namespace("http://example.org/agent/")
ART = Namespace("http://example.org/artifact/")

_namespaces = {
    "ag": AG,
    "art": ART,
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}


def _create_artifact_graph() -> Graph:
    g = Graph()
    for prefix, ns in _namespaces.items():
        g.bind(prefix, ns)
    return g


def load_artifact_graph() -> Graph:
    g = _create_artifact_graph()
    if ARTIFACT_LOG_PATH.exists():
        g.parse(ARTIFACT_LOG_PATH, format="turtle")
    return g


def save_artifact_graph(g: Graph) -> None:
    g.serialize(ARTIFACT_LOG_PATH, format="turtle")


def _get_artifact_count(g: Graph) -> int:
    count = 0
    for _ in g.subjects(RDF.type, ART.Artifact):
        count += 1
    return count


def _compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def log_artifact(
    file_path: str,
    operation: str,
    content: Optional[str] = None,
    previous_hash: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Log an artifact change to RDF."""
    g = load_artifact_graph()

    artifact_id = _get_artifact_count(g)
    artifact_uri = ART[f"change/{artifact_id}"]

    g.add((artifact_uri, RDF.type, ART.Artifact))
    g.add(
        (
            artifact_uri,
            ART.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    g.add((artifact_uri, ART.filePath, Literal(file_path)))
    g.add((artifact_uri, ART.operation, Literal(operation)))

    if content:
        content_hash = _compute_hash(content)
        g.add((artifact_uri, ART.contentHash, Literal(content_hash)))

        if previous_hash:
            g.add((artifact_uri, ART.previousHash, Literal(previous_hash)))
            if previous_hash != content_hash:
                g.add((artifact_uri, ART.changed, Literal(True, datatype=XSD.boolean)))
            else:
                g.add((artifact_uri, ART.changed, Literal(False, datatype=XSD.boolean)))

        if len(content) > 2000:
            content = content[:2000] + "\n... [truncated]"
        g.add((artifact_uri, ART.contentPreview, Literal(content)))

    if metadata:
        if "run_id" in metadata:
            g.add((artifact_uri, ART.runId, Literal(metadata["run_id"])))
        if "task" in metadata:
            g.add((artifact_uri, ART.task, Literal(metadata["task"])))

    save_artifact_graph(g)

    return str(artifact_uri)


def log_file_created(file_path: str, content: str, **kwargs) -> str:
    """Log that a file was created."""
    metadata = {"task": kwargs.pop("task", None), "run_id": kwargs.pop("run_id", None)}
    metadata = {k: v for k, v in metadata.items() if v}
    return log_artifact(
        file_path, "created", content=content, metadata=metadata if metadata else None
    )


def log_file_modified(
    file_path: str, content: str, previous_content: Optional[str] = None, **kwargs
) -> str:
    """Log that a file was modified."""
    previous_hash = _compute_hash(previous_content) if previous_content else None
    metadata = {"task": kwargs.pop("task", None), "run_id": kwargs.pop("run_id", None)}
    metadata = {k: v for k, v in metadata.items() if v}
    return log_artifact(
        file_path,
        "modified",
        content=content,
        previous_hash=previous_hash,
        metadata=metadata if metadata else None,
    )


def log_file_deleted(file_path: str, **kwargs) -> str:
    """Log that a file was deleted."""
    return log_artifact(file_path, "deleted", **kwargs)


def get_artifacts(limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent artifact changes."""
    g = load_artifact_graph()

    artifacts = []
    for artifact in g.subjects(RDF.type, ART.Artifact):
        data = {
            "uri": str(artifact),
            "timestamp": str(g.value(artifact, ART.timestamp) or ""),
            "file_path": str(g.value(artifact, ART.filePath) or ""),
            "operation": str(g.value(artifact, ART.operation) or ""),
            "content_hash": str(g.value(artifact, ART.contentHash) or ""),
            "content_preview": str(g.value(artifact, ART.contentPreview) or ""),
        }

        changed = g.value(artifact, ART.changed)
        if changed:
            data["changed"] = str(changed).lower() == "true"

        previous_hash = g.value(artifact, ART.previousHash)
        if previous_hash:
            data["previous_hash"] = str(previous_hash)

        run_id = g.value(artifact, ART.runId)
        if run_id:
            data["run_id"] = str(run_id)

        task = g.value(artifact, ART.task)
        if task:
            data["task"] = str(task)

        artifacts.append(data)

    artifacts.sort(key=lambda x: x["timestamp"], reverse=True)
    return artifacts[:limit]


def get_artifacts_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Get all artifacts for a specific run."""
    g = load_artifact_graph()

    artifacts = []
    for artifact in g.subjects(ART.runId, Literal(run_id)):
        data = {
            "uri": str(artifact),
            "timestamp": str(g.value(artifact, ART.timestamp) or ""),
            "file_path": str(g.value(artifact, ART.filePath) or ""),
            "operation": str(g.value(artifact, ART.operation) or ""),
            "content_hash": str(g.value(artifact, ART.contentHash) or ""),
        }
        artifacts.append(data)

    return artifacts


def query_artifacts(sparql: str) -> List[Dict[str, Any]]:
    """Query artifacts with custom SPARQL."""
    g = load_artifact_graph()

    results = []
    for row in g.query(sparql):
        result = {}
        for var in row.labels:
            result[var] = str(row[var]) if row[var] else None
        results.append(result)
    return results
