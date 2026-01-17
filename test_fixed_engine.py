#!/usr/bin/env python3
"""
Test the fixed RDF process engine implementation
"""

def test_imports():
    """Test that all imports work"""
    try:
        from bpmn2rdf import BPMNToRDFConverter
        from rdf_process_engine import RDFProcessEngine, ProcessInstance, Token
        from rdflib import Graph

        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality without running processes"""
    try:
        from rdf_process_engine import ProcessInstance, Token

        # Test ProcessInstance creation
        instance = ProcessInstance("http://example.org/process/test")
        print(f"✅ ProcessInstance created: {instance.instance_id}")

        # Test Token creation
        token = Token()
        print(f"✅ Token created: {token.token_id}")

        # Test instance serialization
        data = instance.to_dict()
        print(f"✅ Instance serialization: {data['status']}")

        return True
    except Exception as e:
        print(f"❌ Functionality test failed: {e}")
        return False

def test_bpmn_conversion():
    """Test BPMN to RDF conversion"""
    try:
        from bpmn2rdf import BPMNToRDFConverter

        converter = BPMNToRDFConverter()
        graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
        print(f"✅ BPMN conversion successful: {len(graph)} triples")

        return True
    except Exception as e:
        print(f"❌ BPMN conversion failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Testing Fixed SPEAR RDF Process Engine")
    print("=" * 45)

    success1 = test_imports()
    print()
    success2 = test_basic_functionality()
    print()
    success3 = test_bpmn_conversion()
    print()

    if success1 and success2 and success3:
        print("🎉 All tests passed! The process engine is ready to use.")
    else:
        print("❌ Some tests failed. Please check the error messages above.")