#!/usr/bin/env python3
"""
Quick test of the start event fix
"""

from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine

def test_start_events():
    """Test if start events are now found"""

    # Load BPMN
    converter = BPMNToRDFConverter()
    graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
    print(f"Loaded graph with {len(graph)} triples")

    # Create engine
    engine = RDFProcessEngine(graph)

    # Test finding start events
    try:
        start_events = engine._find_start_events("http://example.org/bpmn/simple_test.bpmn")
        print(f"✅ Found {len(start_events)} start events:")
        for event in start_events:
            print(f"  {event}")

        if len(start_events) > 0:
            return True
        else:
            print("❌ No start events found")
            return False

    except Exception as e:
        print(f"❌ Error finding start events: {e}")
        return False

if __name__ == "__main__":
    success = test_start_events()
    if success:
        print("\n🎉 Start event finding is working!")
    else:
        print("\n❌ Start event finding still broken")