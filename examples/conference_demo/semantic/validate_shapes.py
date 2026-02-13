#!/usr/bin/env python3
"""Validate conference demo RDF data against SHACL core shapes."""

import argparse
import sys
from pathlib import Path

from rdflib import Graph

BASE_DIR = Path(__file__).resolve().parent.parent
SHAPES_FILE = BASE_DIR / "semantic" / "core_shapes.ttl"
DEFAULT_DATA_DIR = BASE_DIR / "run_data"
GRAPH_FILES = ("definitions.ttl", "instances.ttl", "tasks.ttl", "audit.ttl")


def parse_args():
    parser = argparse.ArgumentParser(description="Validate SHACL shapes for conference demo")
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help=f"Directory containing generated RDF files (default: {DEFAULT_DATA_DIR})",
    )
    return parser.parse_args()


def load_data_graph(data_dir: Path) -> Graph:
    graph = Graph()
    for filename in GRAPH_FILES:
        fp = data_dir / filename
        if fp.exists():
            graph.parse(fp, format="turtle")
    return graph


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()

    try:
        from pyshacl import validate
    except ImportError:
        print("pyshacl is not installed. Install it with: pip install pyshacl", file=sys.stderr)
        return 2

    data_graph = load_data_graph(data_dir)
    if len(data_graph) == 0:
        print(f"No RDF data found in {data_dir}", file=sys.stderr)
        return 1

    shapes_graph = Graph().parse(str(SHAPES_FILE), format="turtle")

    conforms, _, results_text = validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="rdfs",
        serialize_report_graph=True,
    )

    print("Conforms:", conforms)
    print(results_text)
    return 0 if conforms else 1


if __name__ == "__main__":
    sys.exit(main())
