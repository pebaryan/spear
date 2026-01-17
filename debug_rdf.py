#!/usr/bin/env python3
"""
Debug RDF graph content to find why start events aren't being detected
"""

from bpmn2rdf import BPMNToRDFConverter
from rdflib import RDF, Namespace

def debug_rdf_graph():
    """Debug what's actually in the RDF graph"""

    converter = BPMNToRDFConverter()
    graph = converter.parse_bpmn_to_graph("simple_test.bpmn")

    print(f"Graph contains {len(graph)} triples")
    print("\n" + "="*50)
    print("ALL TRIPLES:")
    print("="*50)

    for s, p, o in graph:
        print(f"{s} {p} {o}")

    print("\n" + "="*50)
    print("START EVENTS (by type):")
    print("="*50)

    BPMN = Namespace("http://example.org/bpmn/")
    start_events = list(graph.triples((None, RDF.type, BPMN.StartEvent)))
    print(f"Found {len(start_events)} start events:")
    for s, p, o in start_events:
        print(f"  Subject: {s}")
        print(f"  Predicate: {p}")
        print(f"  Object: {o}")
        print()

    print("\n" + "="*50)
    print("ALL TYPES:")
    print("="*50)

    types = {}
    for s, p, o in graph.triples((None, RDF.type, None)):
        type_name = str(o).split('#')[-1] if '#' in str(o) else str(o)
        if type_name not in types:
            types[type_name] = []
        types[type_name].append(str(s))

    for type_name, subjects in types.items():
        print(f"{type_name}: {len(subjects)} instances")
        for subject in subjects:
            print(f"  - {subject}")

if __name__ == "__main__":
    debug_rdf_graph()