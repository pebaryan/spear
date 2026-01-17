#!/usr/bin/env python3
"""
Test script to check for syntax and import errors
"""

print("Testing imports...")

try:
    from src.conversion import BPMNToRDFConverter
    print("✅ BPMNToRDFConverter import successful")
except Exception as e:
    print(f"❌ BPMNToRDFConverter import failed: {e}")

try:
    from src.core import RDFProcessEngine, ProcessInstance, Token
    print("✅ RDFProcessEngine import successful")
except Exception as e:
    print(f"❌ RDFProcessEngine import failed: {e}")

try:
    from rdflib import Graph
    print("✅ rdflib import successful")
except Exception as e:
    print(f"❌ rdflib import failed: {e}")

print("\nTesting basic instantiation...")

try:
    converter = BPMNToRDFConverter()
    print("✅ BPMNToRDFConverter instantiation successful")
except Exception as e:
    print(f"❌ BPMNToRDFConverter instantiation failed: {e}")

print("All tests completed.")