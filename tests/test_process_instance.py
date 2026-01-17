#!/usr/bin/env python3
"""
Test the complete process instance start/stop functionality using pytest assertions
"""

from src.conversion import BPMNToRDFConverter
from src.core import RDFProcessEngine
import time
import os
import pytest


def test_basic_process_instance():
    """Test basic process instance start and stop"""
    print("\n🧪 Testing Basic Process Instance Management")
    print("=" * 50)

    # Step 1: Load BPMN process definition
    print("\n1. Loading BPMN Process Definition...")
    converter = BPMNToRDFConverter()
    bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")
    definition_graph = converter.parse_bpmn_to_graph(bpmn_path)
    assert len(definition_graph) > 0, "Failed to load BPMN definition"
    print(f"✅ Loaded process definition with {len(definition_graph)} triples")

    # Step 2: Initialize Process Engine
    print("\n2. Initializing Process Engine...")
    engine = RDFProcessEngine(definition_graph)
    print("✅ Process engine initialized")

    # Step 3: Register a service task handler
    def simple_handler(context):
        """Simple handler that does nothing"""
        customer = context.get_variable("customer_name") or "Unknown"
        print(f"⚡ Processing order for {customer}")

    engine.register_topic_handler("process_order", simple_handler)
    print("✅ Registered service task handler")

    # Step 4: Start Process Instance
    print("\n3. Starting Process Instance...")
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

    # Assertions
    assert instance is not None, "Instance should be created"
    assert instance.instance_id is not None, "Instance should have an ID"
    assert instance.status in ["CREATED", "RUNNING", "COMPLETED"], f"Unexpected status: {instance.status}"
    assert len(instance.tokens) > 0, "Instance should have at least one token"

    # Give it a moment to execute
    time.sleep(0.1)

    # Check final status
    status = engine.get_instance_status(instance.instance_id)
    assert status is not None, "Should be able to get instance status"
    print(f"   Final Status: {status['status']}")
    print("✅ Process instance test completed successfully")


def test_stop_instance():
    """Test stopping a process instance"""
    print("\n4. Testing Process Instance Stop...")
    
    converter = BPMNToRDFConverter()
    bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")
    definition_graph = converter.parse_bpmn_to_graph(bpmn_path)
    engine = RDFProcessEngine(definition_graph)

    # Start instance
    instance = engine.start_process_instance(
        process_definition_uri="http://example.org/bpmn/simple_test.bpmn"
    )
    print(f"Started instance: {instance.instance_id}")
    assert instance is not None, "Instance should be created"

    # Stop instance
    stopped = engine.stop_process_instance(instance.instance_id, "Test stop")
    assert stopped is True, "Stop operation should return True"
    print(f"Stop result: {stopped}")

    # Check status
    status = engine.get_instance_status(instance.instance_id)
    assert status is not None, "Should be able to get instance status"
    assert status['status'] == 'TERMINATED', f"Expected TERMINATED status, got {status['status']}"
    print(f"Final status: {status['status']}")
    print("✅ Process instance stop test completed successfully")


if __name__ == "__main__":
    # Allow running tests directly without pytest
    print("Running tests directly (use pytest for proper test framework)...")
    print()
    
    try:
        test_basic_process_instance()
        print("\n✅ test_basic_process_instance PASSED")
    except Exception as e:
        print(f"\n❌ test_basic_process_instance FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    
    try:
        test_stop_instance()
        print("\n✅ test_stop_instance PASSED")
    except Exception as e:
        print(f"\n❌ test_stop_instance FAILED: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("Direct test execution complete")