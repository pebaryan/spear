#!/usr/bin/env python3
"""
Quick fix: Update the process engine to work with the current RDF structure
"""

from rdf_process_engine import RDFProcessEngine
from bpmn2rdf import BPMNToRDFConverter

# Load the BPMN file
converter = BPMNToRDFConverter()
graph = converter.parse_bpmn_to_graph("simple_test.bpmn")

print(f"Loaded graph with {len(graph)} triples")

# Check what's actually in the graph
from rdflib import RDF, Namespace
BPMN = Namespace("http://example.org/bpmn/")

print("\nStart events:")
for s, p, o in graph.triples((None, RDF.type, BPMN.StartEvent)):
    print(f"  {s}")

print("\nProcesses:")
for s, p, o in graph.triples((None, RDF.type, BPMN.Process)):
    print(f"  {s}")

print("\nAll hasParent relationships:")
for s, p, o in graph.triples((None, BPMN.hasParent, None)):
    print(f"  {s} hasParent {o}")

# Test the actual query
query = """
SELECT ?start WHERE {
    ?start rdf:type bpmn:StartEvent .
    ?process rdf:type bpmn:Process .
    ?start bpmn:hasParent ?process .
}
"""

results = list(graph.query(query))
print(f"\nSPARQL query results: {len(results)}")
for row in results:
    print(f"  Found start event: {row[0]}")