#!/usr/bin/env python3
"""
Debug the start event finding issue
"""

from bpmn2rdf import BPMNToRDFConverter
from rdflib import Graph

def debug_start_events():
    """Debug the start event finding"""

    # Load BPMN and convert to RDF
    converter = BPMNToRDFConverter()
    graph = converter.parse_bpmn_to_graph("simple_test.bpmn")

    print(f"Graph contains {len(graph)} triples")
    print("\nAll triples:")
    for s, p, o in graph:
        print(f"  {s} {p} {o}")

    # Check for start events
    print("\nChecking for start events...")
    from rdflib import RDF, URIRef, Namespace
    BPMN = Namespace("http://example.org/bpmn/")

    start_events = list(graph.triples((None, RDF.type, BPMN.StartEvent)))
    print(f"Found {len(start_events)} start events:")
    for s, p, o in start_events:
        print(f"  {s}")

    # Check for processes
    processes = list(graph.triples((None, RDF.type, BPMN.Process)))
    print(f"\nFound {len(processes)} processes:")
    for s, p, o in processes:
        print(f"  {s}")

    # Check parent relationships
    print("\nParent relationships:")
    parent_rels = list(graph.triples((None, BPMN.hasParent, None)))
    for s, p, o in parent_rels:
        print(f"  {s} hasParent {o}")

    # Test the SPARQL query
    print("\nTesting SPARQL query:")
    query = """
    SELECT ?start WHERE {
        ?start rdf:type bpmn:StartEvent .
        ?process rdf:type bpmn:Process .
        ?start bpmn:hasParent ?process .
    }
    """

    results = list(graph.query(query))
    print(f"SPARQL query found {len(results)} results:")
    for row in results:
        print(f"  {row[0]}")

if __name__ == "__main__":
    debug_start_events()