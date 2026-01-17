#!/usr/bin/env python3
"""
Minimal test to check if start events are in the graph
"""

from bpmn2rdf import BPMNToRDFConverter
from rdflib import RDF, Namespace

# Convert BPMN to Graph
converter = BPMNToRDFConverter()
graph = converter.parse_bpmn_to_graph("simple_test.bpmn")

print(f"Graph has {len(graph)} triples")

# Check all triples with rdf:type
print("\nAll triples with rdf:type:")
for s, p, o in graph.triples((None, RDF.type, None)):
    print(f"  {s} a {o}")

# Check specifically for StartEvent
BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
print(f"\nLooking for: {BPMN.StartEvent}")

start_events = list(graph.triples((None, RDF.type, BPMN.StartEvent)))
print(f"Found {len(start_events)} start events")

# Also try without namespace
print("\nAll types in graph:")
types = {}
for s, p, o in graph.triples((None, RDF.type, None)):
    types[str(o)] = types.get(str(o), 0) + 1

for t, count in sorted(types.items()):
    print(f"  {t}: {count}")