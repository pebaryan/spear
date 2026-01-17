#!/usr/bin/env python3
"""
Verify that the package structure works correctly with proper exports
"""

print("=" * 70)
print("VERIFICATION: Testing Package Imports and Exports")
print("=" * 70)

# Test 1: Import from src (top-level package)
print("\n1. Testing top-level imports from src package...")
try:
    from src import BPMNToRDFConverter, RDFProcessEngine, ProcessInstance, Token
    print("✅ Successfully imported from src (top-level)")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 2: Import from src.core
print("\n2. Testing imports from src.core...")
try:
    from src.core import RDFEngine, ProcessContext, RDFProcessEngine, ProcessInstance, Token
    print("✅ Successfully imported all classes from src.core")
    print("   - RDFEngine")
    print("   - ProcessContext")
    print("   - RDFProcessEngine")
    print("   - ProcessInstance")
    print("   - Token")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 3: Import from src.conversion
print("\n3. Testing imports from src.conversion...")
try:
    from src.conversion import BPMNToRDFConverter
    print("✅ Successfully imported BPMNToRDFConverter from src.conversion")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 4: Import from src.export
print("\n4. Testing imports from src.export...")
try:
    from src.export import export_to_xes_csv
    print("✅ Successfully imported export_to_xes_csv from src.export")
except Exception as e:
    print(f"❌ Failed: {e}")

# Test 5: Instantiate classes
print("\n5. Testing class instantiation...")
try:
    converter = BPMNToRDFConverter()
    print("✅ Instantiated BPMNToRDFConverter")

    instance = ProcessInstance("http://example.org/test")
    print(f"✅ Instantiated ProcessInstance: {instance.instance_id[:8]}...")

    token = Token()
    print(f"✅ Instantiated Token: {token.token_id[:8]}...")

except Exception as e:
    print(f"❌ Failed: {e}")

# Test 6: Load and parse BPMN file
print("\n6. Testing BPMN file loading...")
try:
    import os
    bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")

    if os.path.exists(bpmn_path):
        converter = BPMNToRDFConverter()
        graph = converter.parse_bpmn_to_graph(bpmn_path)
        print(f"✅ Loaded and parsed BPMN file: {len(graph)} triples")
    else:
        print(f"❌ BPMN file not found at: {bpmn_path}")

except Exception as e:
    print(f"❌ Failed: {e}")

# Test 7: Check __all__ exports
print("\n7. Checking package exports (__all__)...")
try:
    import src
    exports = src.__all__
    print(f"✅ Package exports {len(exports)} items:")
    for item in exports:
        print(f"   - {item}")
except Exception as e:
    print(f"❌ Failed: {e}")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)

print("\n📚 Usage Examples:")
print("-" * 70)
print("from src import BPMNToRDFConverter, RDFProcessEngine")
print("from src.core import RDFEngine, ProcessContext")
print("from src.conversion import BPMNToRDFConverter")
print("from src.export import export_to_xes_csv")
print("-" * 70)