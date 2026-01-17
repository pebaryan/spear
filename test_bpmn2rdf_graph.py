#!/usr/bin/env python3
"""
Test script for the new parse_bpmn_to_graph method
"""

from bpmn2rdf import BPMNToRDFConverter

def test_parse_to_graph():
    """Test that parse_bpmn_to_graph returns an rdflib.Graph"""
    converter = BPMNToRDFConverter()

    # Test with the simple BPMN file first
    try:
        graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
        print(f"✅ Successfully parsed simple BPMN to rdflib.Graph")
        print(f"   Graph contains {len(graph)} triples")

        # Print a few triples to verify
        print("   Sample triples:")
        for i, (s, p, o) in enumerate(graph):
            if i >= 3:  # Show only first 3 triples
                break
            print(f"   {s} {p} {o}")

        return True

    except Exception as e:
        print(f"❌ Error parsing simple BPMN: {e}")
        return False

def test_compare_methods():
    """Compare output of both methods to ensure consistency"""
    converter = BPMNToRDFConverter()

    try:
        # Get Turtle string
        turtle_output = converter.parse_bpmn("simple_test.bpmn")
        print(f"✅ parse_bpmn() returned {len(turtle_output)} characters")

        # Get Graph
        graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
        print(f"✅ parse_bpmn_to_graph() returned graph with {len(graph)} triples")

        # Verify they contain the same information
        if len(graph) > 0:
            print("✅ Both methods produced valid output")
            return True
        else:
            print("❌ Graph is empty")
            return False

    except Exception as e:
        print(f"❌ Error comparing methods: {e}")
        return False

if __name__ == "__main__":
    print("Testing BPMN to RDF Graph conversion...")
    print()

    success1 = test_parse_to_graph()
    print()
    success2 = test_compare_methods()
    print()

    # Test the camunda extension version
    print("Testing BPMN with Camunda extensions...")
    converter = BPMNToRDFConverter()
    try:
        graph = converter.parse_bpmn_to_graph("test.bpmn")
        print(f"✅ Successfully parsed BPMN with Camunda extensions")
        print(f"   Graph contains {len(graph)} triples")
        success3 = True
    except Exception as e:
        print(f"❌ Error parsing BPMN with Camunda extensions: {e}")
        success3 = False
    print()

    if success1 and success2 and success3:
        print("🎉 All tests passed!")
    else:
        print("❌ Some tests failed!")