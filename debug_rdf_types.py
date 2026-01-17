#!/usr/bin/env python3
"""
Debug the actual RDF content to find the namespace/type issue
"""

from bpmn2rdf import BPMNToRDFConverter
from rdflib import Graph, RDF, Namespace

# Load the BPMN and convert to RDF
converter = BPMNToRDFConverter()
graph = converter.parse_bpmn_to_graph("simple_test.bpmn")

print(f"Graph contains {len(graph)} triples")

# Check all types
print("\n" + "="*60)
print("ALL RDF TYPES IN GRAPH:")
print("="*60)

types_found = {}
for s, p, o in graph.triples((None, RDF.type, None)):
    type_str = str(o)
    if type_str not in types_found:
        types_found[type_str] = []
    types_found[type_str].append(str(s))

for type_uri, subjects in sorted(types_found.items()):
    print(f"\n{type_uri}:")
    for subject in subjects:
        print(f"  - {subject}")

# Check specific for StartEvent with different possible namespaces
print("\n" + "="*60)
print("CHECKING FOR START EVENTS WITH DIFFERENT NAMESPACES:")
print("="*60)

# Try the converter's namespace
BPMN_conv = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
start_events1 = list(graph.triples((None, RDF.type, BPMN_conv.StartEvent)))
print(f"\nWith converter namespace (http://dkm.fbk.eu/index.php/BPMN2_Ontology#):")
print(f"  Found {len(start_events1)} start events")

# Try the old namespace
BPMN_old = Namespace("http://example.org/bpmn/")
start_events2 = list(graph.triples((None, RDF.type, BPMN_old.StartEvent)))
print(f"\nWith old namespace (http://example.org/bpmn/):")
print(f"  Found {len(start_events2)} start events")

# Print sample triples to see the actual format
print("\n" + "="*60)
print("SAMPLE TRIPLES (first 10):")
print("="*60)
for i, (s, p, o) in enumerate(graph):
    if i >= 10:
        break
    print(f"{s}")
    print(f"  {p}")
    print(f"  {o}")
    print()