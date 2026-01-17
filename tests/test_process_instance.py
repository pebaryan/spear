#!/usr/bin/env python3
"""
Test the complete process instance start/stop functionality
"""

from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine
import time

def test_basic_process_instance():
    """Test basic process instance start and stop"""

    print("🧪 Testing Basic Process Instance Management")
    print("=" * 50)

    # Step 1: Load BPMN process definition
    print("\n1. Loading BPMN Process Definition...")
    converter = BPMNToRDFConverter()
    try:
        definition_graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
        print(f"✅ Loaded process definition with {len(definition_graph)} triples")
    except Exception as e:
        print(f"❌ Failed to load process definition: {e}")
        return False

    # Step 2: Initialize Process Engine
    print("\n2. Initializing Process Engine...")
    engine = RDFProcessEngine(definition_graph)
    print("✅ Process engine initialized")

    # Step 3: Register a service task handler (if needed)
    def simple_handler(context):
        """Simple handler that does nothing"""
        customer = context.get_variable("customer_name") or "Unknown"
        print(f"⚡ Processing order for {customer}")

    engine.register_topic_handler("process_order", simple_handler)
    print("✅ Registered service task handler")

    # Step 4: Start Process Instance
    print("\n3. Starting Process Instance...")
    try:
        instance = engine.start_process_instance(
            process_definition_uri="http://example.org/bpmn/simple_test.bpmn",
            initial_variables={
                "customer_name": "Test Customer",
                "order_total": 99.99
            }
        )

        print("✅ Started process instance:")
        print(f"   Instance ID: {instance.instance_id}")
        print(f"   Status: {instance.status}")
        print(f"   Tokens: {len(instance.tokens)}")

        # Give it a moment to execute
        time.sleep(0.1)

        # Check final status
        status = engine.get_instance_status(instance.instance_id)
        print(f"   Final Status: {status['status'] if status else 'Unknown'}")

        return True

    except Exception as e:
        print(f"❌ Failed to start process instance: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_stop_instance():
    """Test stopping a process instance"""

    print("\n4. Testing Process Instance Stop...")
    converter = BPMNToRDFConverter()
    definition_graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
    engine = RDFProcessEngine(definition_graph)

    # Start instance
    instance = engine.start_process_instance(
        process_definition_uri="http://example.org/bpmn/simple_test.bpmn"
    )

    print(f"Started instance: {instance.instance_id}")

    # Stop instance
    stopped = engine.stop_process_instance(instance.instance_id, "Test stop")
    print(f"Stop result: {stopped}")

    # Check status
    status = engine.get_instance_status(instance.instance_id)
    if status:
        print(f"Final status: {status['status']}")
        return status['status'] == 'TERMINATED'
    else:
        print("❌ Could not get instance status")
        return False

if __name__ == "__main__":
    success1 = test_basic_process_instance()
    print()
    success2 = test_stop_instance()

    print("\n" + "=" * 50)
    if success1 and success2:
        print("🎉 All tests passed! Process instance management is working.")
    else:
        print("❌ Some tests failed.")