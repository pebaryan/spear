#!/usr/bin/env python3
"""
Test the namespace fix
"""

from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine
from rdflib import RDF, Namespace

# Load BPMN
converter = BPMNToRDFConverter()
graph = converter.parse_bpmn_to_graph("simple_test.bpmn")

print(f"Loaded graph with {len(graph)} triples")

# Check with correct namespace
BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")

print("\nChecking start events with correct namespace:")
start_events = list(graph.triples((None, RDF.type, BPMN.StartEvent)))
print(f"Found {len(start_events)} start events")
for s, p, o in start_events:
    print(f"  {s}")

# Test engine
engine = RDFProcessEngine(graph)
start_events_found = engine._find_start_events("http://example.org/bpmn/simple_test.bpmn")
print(f"\nEngine found {len(start_events_found)} start events:")
for event in start_events_found:
    print(f"  {event}")