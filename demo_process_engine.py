#!/usr/bin/env python3
"""
Demonstration of starting and stopping process instances using RDFProcessEngine
"""

from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine
import time

def demo_process_instance_management():
    """Demonstrate process instance start/stop functionality"""

    print("🚀 SPEAR Process Engine Demo")
    print("=" * 50)

    # Step 1: Load BPMN process definition
    print("\n1. Loading BPMN Process Definition...")
    converter = BPMNToRDFConverter()
    try:
        definition_graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
        print(f"✅ Loaded process definition with {len(definition_graph)} triples")
    except Exception as e:
        print(f"❌ Failed to load process definition: {e}")
        return

    # Step 2: Initialize Process Engine
    print("\n2. Initializing Process Engine...")
    engine = RDFProcessEngine(definition_graph)
    print("✅ Process engine initialized")

    # Step 3: Register a service task handler
    print("\n3. Registering Service Task Handler...")
    def process_order_handler(context):
        """Simple service task handler"""
        order_total = float(context.get_variable("order_total") or 100.0)
        print(f"📦 Processing order with total: ${order_total}")
        # Simulate processing time
        time.sleep(0.1)
        # Set result variable
        context.set_variable("processing_status", "completed")

    engine.register_topic_handler("process_order", process_order_handler)
    print("✅ Registered handler for 'process_order' topic")

    # Step 4: Start Process Instance
    print("\n4. Starting Process Instance...")
    try:
        # Define initial variables
        initial_vars = {
            "customer_name": "John Doe",
            "order_total": 150.50,
            "order_items": ["Widget A", "Widget B"]
        }

        instance = engine.start_process_instance(
            process_definition_uri="http://example.org/bpmn/simple_test.bpmn",
            initial_variables=initial_vars
        )

        print("✅ Started process instance:")
        print(f"   Instance ID: {instance.instance_id}")
        print(f"   Status: {instance.status}")
        print(f"   Tokens: {len(instance.tokens)}")

        # Show instance details
        status = engine.get_instance_status(instance.instance_id)
        if status:
            print(f"   Created: {status['created_at']}")
            print(f"   Variables: customer_name={initial_vars['customer_name']}")

    except Exception as e:
        print(f"❌ Failed to start process instance: {e}")
        return

    # Step 5: Monitor Instance Execution
    print("\n5. Monitoring Instance Execution...")
    time.sleep(0.2)  # Allow some execution time

    status = engine.get_instance_status(instance.instance_id)
    if status:
        print(f"   Current status: {status['status']}")
        print(f"   Active tokens: {status['token_count']}")

    # Step 6: Stop Process Instance
    print("\n6. Stopping Process Instance...")
    try:
        stopped = engine.stop_process_instance(
            instance.instance_id,
            reason="Demo completion"
        )

        if stopped:
            print("✅ Successfully stopped process instance")
            status = engine.get_instance_status(instance.instance_id)
            if status:
                print(f"   Final status: {status['status']}")
        else:
            print("❌ Failed to stop process instance")

    except Exception as e:
        print(f"❌ Error stopping instance: {e}")

    # Step 7: List All Instances
    print("\n7. Listing All Process Instances...")
    instances = engine.list_instances()
    print(f"   Total instances: {len(instances)}")
    for inst in instances:
        print(f"   - {inst['instance_id']}: {inst['status']} ({inst['token_count']} tokens)")

    print("\n🎉 Demo completed successfully!")

def demo_multiple_instances():
    """Demonstrate running multiple instances simultaneously"""

    print("\n\n📊 Multiple Instances Demo")
    print("=" * 30)

    # Setup
    converter = BPMNToRDFConverter()
    definition_graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
    engine = RDFProcessEngine(definition_graph)

    def quick_handler(context):
        customer = context.get_variable("customer_name")
        print(f"⚡ Quick processing for {customer}")

    engine.register_topic_handler("process_order", quick_handler)

    # Start multiple instances
    instances = []
    customers = ["Alice", "Bob", "Charlie", "Diana"]

    for i, customer in enumerate(customers):
        try:
            instance = engine.start_process_instance(
                process_definition_uri="http://example.org/bpmn/simple_test.bpmn",
                initial_variables={"customer_name": customer, "order_total": (i+1) * 50}
            )
            instances.append(instance)
            print(f"✅ Started instance for {customer}: {instance.instance_id}")
        except Exception as e:
            print(f"❌ Failed to start instance for {customer}: {e}")

    time.sleep(0.3)  # Allow execution

    # Check status of all instances
    print("\nInstance Status Summary:")
    all_instances = engine.list_instances()
    for inst in all_instances:
        print(f"   {inst['instance_id'][:8]}...: {inst['status']}")

    # Stop one instance
    if instances:
        target_instance = instances[0]
        print(f"\nStopping instance: {target_instance.instance_id}")
        engine.stop_process_instance(target_instance.instance_id, "Demo cleanup")

        # Check final status
        status = engine.get_instance_status(target_instance.instance_id)
        print(f"   Final status: {status['status'] if status else 'Not found'}")

if __name__ == "__main__":
    demo_process_instance_management()
    demo_multiple_instances()