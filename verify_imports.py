#!/usr/bin/env python3
"""
Quick verification that all imports work with the new structure
"""

print("=" * 60)
print("VERIFYING IMPORTS WITH NEW STRUCTURE")
print("=" * 60)

# Test 1: Import from src.conversion
print("\n1. Testing src.conversion import...")
try:
    from src.conversion import BPMNToRDFConverter
    print("✅ Successfully imported BPMNToRDFConverter from src.conversion")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 2: Import from src.core
print("\n2. Testing src.core imports...")
try:
    from src.core import RDFEngine, RDFProcessEngine, ProcessContext, ProcessInstance, Token
    print("✅ Successfully imported all classes from src.core")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 3: Import from src.export
print("\n3. Testing src.export import...")
try:
    from src.export import sparql2xe  # or whatever is exported
    print("✅ Successfully imported from src.export")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 4: Import rdflib
print("\n4. Testing rdflib import...")
try:
    from rdflib import Graph, RDF, Namespace, Literal
    print("✅ Successfully imported rdflib modules")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 5: Instantiate classes
print("\n5. Testing class instantiation...")
try:
    converter = BPMNToRDFConverter()
    print("✅ Successfully instantiated BPMNToRDFConverter")

    instance = ProcessInstance("http://example.org/test")
    print(f"✅ Successfully instantiated ProcessInstance: {instance.instance_id[:8]}...")

    token = Token()
    print(f"✅ Successfully instantiated Token: {token.token_id[:8]}...")

except Exception as e:
    print(f"❌ Failed: {e}")

# Test 6: Load BPMN file from new location
print("\n6. Testing BPMN file loading from new structure...")
try:
    import os
    bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")
    if os.path.exists(bpmn_path):
        graph = converter.parse_bpmn_to_graph(bpmn_path)
        print(f"✅ Successfully loaded BPMN file with {len(graph)} triples")
    else:
        print(f"❌ BPMN file not found at: {bpmn_path}")
except Exception as e:
    print(f"❌ Failed: {e}")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)