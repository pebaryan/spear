#!/usr/bin/env python3
"""
Check the actual Turtle output
"""

from bpmn2rdf import BPMNToRDFConverter

converter = BPMNToRDFConverter()
turtle = converter.parse_bpmn("simple_test.bpmn")

print(turtle)