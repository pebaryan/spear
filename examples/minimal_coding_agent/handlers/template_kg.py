"""RDF-backed repair template knowledge graph."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from rdflib import Graph, Literal, Namespace, RDF, RDFS, XSD

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_GRAPH_PATH = BASE_DIR / "template_knowledge.ttl"

AG = Namespace("http://example.org/agent/")
TEMP = Namespace("http://example.org/template/")
VAR = Namespace("http://example.org/variables/")

DEFAULT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "off_by_one_fix": {
        "description": "Fix expressions like count + 1 / 1 + count when tests indicate off-by-one.",
        "weight": 1.15,
    },
    "boundary_guard": {
        "description": "Adjust guard comparisons for boundary checks (e.g., < to <= at zero boundary).",
        "weight": 1.05,
    },
    "arithmetic_swap": {
        "description": "Swap arithmetic operators (+,-,*,/) as low-confidence exploratory mutation.",
        "weight": 0.85,
    },
    "operator_swap": {
        "description": "Swap comparison operators (==, !=, <, <=, >, >=) when mismatch is likely.",
        "weight": 0.95,
    },
    "generic": {
        "description": "Generic fallback mutation template.",
        "weight": 1.0,
    },
}


def _create_graph() -> Graph:
    g = Graph()
    g.bind("ag", AG)
    g.bind("temp", TEMP)
    g.bind("var", VAR)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)
    return g


def load_template_graph(path: Path = TEMPLATE_GRAPH_PATH) -> Graph:
    g = _create_graph()
    if path.exists():
        g.parse(path, format="turtle")
    return g


def save_template_graph(g: Graph, path: Path = TEMPLATE_GRAPH_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(path, format="turtle")


def _template_uri(name: str):
    return TEMP[f"template/{name}"]


def ensure_default_templates(path: Path = TEMPLATE_GRAPH_PATH) -> None:
    g = load_template_graph(path)
    changed = False

    for name, meta in DEFAULT_TEMPLATES.items():
        uri = _template_uri(name)
        if (uri, RDF.type, TEMP.RepairTemplate) not in g:
            g.add((uri, RDF.type, TEMP.RepairTemplate))
            changed = True

        if (uri, TEMP.name, None) not in g:
            g.add((uri, TEMP.name, Literal(name)))
            changed = True

        if (uri, RDFS.comment, None) not in g:
            g.add((uri, RDFS.comment, Literal(meta["description"])))
            changed = True

        if (uri, TEMP.weight, None) not in g:
            g.add(
                (
                    uri,
                    TEMP.weight,
                    Literal(float(meta["weight"]), datatype=XSD.float),
                )
            )
            changed = True

    if changed:
        save_template_graph(g, path)


def get_template_weights(path: Path = TEMPLATE_GRAPH_PATH) -> Dict[str, float]:
    ensure_default_templates(path)
    g = load_template_graph(path)

    weights: Dict[str, float] = {}
    for template_uri in g.subjects(RDF.type, TEMP.RepairTemplate):
        name_value = g.value(template_uri, TEMP.name)
        weight_value = g.value(template_uri, TEMP.weight)
        if not name_value or weight_value is None:
            continue
        name = str(name_value)
        try:
            weight = float(weight_value)
        except Exception:
            continue
        if weight <= 0:
            continue
        weights[name] = weight
    return weights


def update_template_weights(
    weights: Dict[str, float],
    stats: Optional[Dict[str, Dict[str, Any]]] = None,
    source: str = "",
    eval_file: str = "",
    min_support: int = 0,
    path: Path = TEMPLATE_GRAPH_PATH,
) -> None:
    ensure_default_templates(path)
    g = load_template_graph(path)

    calibration_uri = TEMP[f"calibration/{datetime.now().strftime('%Y%m%d%H%M%S%f')}"]
    g.add((calibration_uri, RDF.type, TEMP.TemplateCalibration))
    g.add(
        (
            calibration_uri,
            TEMP.timestamp,
            Literal(datetime.now().isoformat(), datatype=XSD.dateTime),
        )
    )
    if source:
        g.add((calibration_uri, TEMP.source, Literal(source)))
    if eval_file:
        g.add((calibration_uri, TEMP.evalFile, Literal(eval_file)))
    if min_support:
        g.add(
            (
                calibration_uri,
                TEMP.minSupport,
                Literal(int(min_support), datatype=XSD.integer),
            )
        )

    for name, weight in (weights or {}).items():
        try:
            numeric_weight = float(weight)
        except Exception:
            continue
        if numeric_weight <= 0:
            continue

        template_uri = _template_uri(str(name))
        if (template_uri, RDF.type, TEMP.RepairTemplate) not in g:
            g.add((template_uri, RDF.type, TEMP.RepairTemplate))
        if (template_uri, TEMP.name, None) not in g:
            g.add((template_uri, TEMP.name, Literal(str(name))))

        g.remove((template_uri, TEMP.weight, None))
        g.add((template_uri, TEMP.weight, Literal(numeric_weight, datatype=XSD.float)))
        g.add((calibration_uri, TEMP.updatedTemplate, template_uri))

        item_stats = (stats or {}).get(str(name), {})
        if isinstance(item_stats, dict):
            if "support" in item_stats:
                try:
                    g.remove((template_uri, TEMP.support, None))
                    g.add(
                        (
                            template_uri,
                            TEMP.support,
                            Literal(int(item_stats["support"]), datatype=XSD.integer),
                        )
                    )
                except Exception:
                    pass
            if "success_rate" in item_stats:
                try:
                    g.remove((template_uri, TEMP.successRate, None))
                    g.add(
                        (
                            template_uri,
                            TEMP.successRate,
                            Literal(
                                float(item_stats["success_rate"]),
                                datatype=XSD.float,
                            ),
                        )
                    )
                except Exception:
                    pass

    save_template_graph(g, path)
