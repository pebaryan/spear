#!/usr/bin/env python3
"""
Quick check of RDF graph content
"""

from bpmn2rdf import BPMNToRDFConverter
from rdflib import RDF, Namespace

converter = BPMNToRDFConverter()
graph = converter.parse_bpmn_to_graph("simple_test.bpmn")

print(f"Graph contains {len(graph)} triples")

BPMN = Namespace("http://example.org/bpmn/")

print("\nStart events:")
for s, p, o in graph.triples((None, RDF.type, BPMN.StartEvent)):
    print(f"  {s}")

print("\nAll node types:")
types = {}
for s, p, o in graph.triples((None, RDF.type, None)):
    type_uri = str(o)
    type_name = type_uri.split('#')[-1] if '#' in type_uri else type_uri.split('/')[-1]
    if type_name not in types:
        types[type_name] = 0
    types[type_name] += 1

for type_name, count in types.items():
    print(f"  {type_name}: {count}")