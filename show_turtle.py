#!/usr/bin/env python3
"""
Print the actual Turtle output to see what types are generated
"""

from bpmn2rdf import BPMNToRDFConverter

converter = BPMNToRDFConverter()
turtle_output = converter.parse_bpmn("simple_test.bpmn")

print("TURTLE OUTPUT:")
print("="*60)
print(turtle_output)
print("="*60)