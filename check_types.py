#!/usr/bin/env python3
"""
Check what types the converter creates
"""

from bpmn2rdf import BPMNToRDFConverter

converter = BPMNToRDFConverter()
turtle_output = converter.parse_bpmn("simple_test.bpmn")

print("Turtle output:")
print(turtle_output)

# Parse the Turtle to see what types are created
from rdflib import Graph
graph = Graph()
graph.parse(data=turtle_output, format='turtle')

from rdflib import RDF
print(f"\nGraph has {len(graph)} triples")

print("\nAll types found:")
for s, p, o in graph.triples((None, RDF.type, None)):
    print(f"  {s} -> {o}")