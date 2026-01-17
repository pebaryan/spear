#!/usr/bin/env python3
"""
Test script to check for syntax and import errors using pytest
"""

def test_imports():
    """Test that all imports work correctly"""
    print("Testing imports...")

    # Test src.conversion import
    from src.conversion import BPMNToRDFConverter
    assert BPMNToRDFConverter is not None

    # Test src.core imports
    from src.core import RDFProcessEngine, ProcessInstance, Token
    assert RDFProcessEngine is not None
    assert ProcessInstance is not None
    assert Token is not None

    # Test rdflib import
    from rdflib import Graph
    assert Graph is not None
    
    print("✅ All imports successful")


def test_instantiation():
    """Test that classes can be instantiated"""
    print("\nTesting basic instantiation...")

    from src.conversion import BPMNToRDFConverter
    
    converter = BPMNToRDFConverter()
    assert converter is not None
    
    print("✅ All instantiations successful")


if __name__ == "__main__":
    # Run tests directly
    print("Running import tests...")
    print("=" * 60)
    
    try:
        test_imports()
        print("\n✅ test_imports PASSED")
    except Exception as e:
        print(f"\n❌ test_imports FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    
    try:
        test_instantiation()
        print("\n✅ test_instantiation PASSED")
    except Exception as e:
        print(f"\n❌ test_instantiation FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Direct test execution complete")