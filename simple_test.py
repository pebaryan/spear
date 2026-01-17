#!/usr/bin/env python3
"""
Simple test to check if the RDF process engine can be imported and instantiated
"""

def test_basic_import():
    """Test basic import and instantiation"""
    try:
        from bpmn2rdf import BPMNToRDFConverter
        print("✅ BPMNToRDFConverter imported successfully")

        converter = BPMNToRDFConverter()
        print("✅ BPMNToRDFConverter instantiated successfully")

        return True
    except Exception as e:
        print(f"❌ BPMNToRDFConverter error: {e}")
        return False

def test_process_engine_import():
    """Test RDF process engine import"""
    try:
        from rdf_process_engine import RDFProcessEngine, ProcessInstance, Token
        print("✅ RDFProcessEngine classes imported successfully")

        from rdflib import Graph
        print("✅ rdflib imported successfully")

        return True
    except Exception as e:
        print(f"❌ RDFProcessEngine import error: {e}")
        return False

def test_basic_instantiation():
    """Test basic object instantiation"""
    try:
        from rdf_process_engine import ProcessInstance, Token
        from rdflib import URIRef

        # Test ProcessInstance
        instance = ProcessInstance("http://example.org/process/test")
        print(f"✅ ProcessInstance created: {instance.instance_id}")

        # Test Token
        token = Token()
        print(f"✅ Token created: {token.token_id}")

        return True
    except Exception as e:
        print(f"❌ Instantiation error: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing SPEAR RDF Process Engine")
    print("=" * 40)

    success1 = test_basic_import()
    print()
    success2 = test_process_engine_import()
    print()
    success3 = test_basic_instantiation()
    print()

    if success1 and success2 and success3:
        print("🎉 All basic tests passed!")
    else:
        print("❌ Some tests failed - check the error messages above")