# SPEAR RDF Process Engine Usage Guide

## Overview

The `RDFProcessEngine` provides complete process instance lifecycle management for BPMN processes stored as RDF graphs. It supports starting, stopping, and monitoring process instances with token-based execution.

## Basic Usage

```python
from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine

# 1. Load BPMN process definition
converter = BPMNToRDFConverter()
definition_graph = converter.parse_bpmn_to_graph("myprocess.bpmn")

# 2. Initialize process engine
engine = RDFProcessEngine(definition_graph)

# 3. Register service task handlers (optional)
def process_order(context):
    order_total = float(context.get_variable("order_total"))
    print(f"Processing order: ${order_total}")
    context.set_variable("status", "processed")

engine.register_topic_handler("process_order", process_order)

# 4. Start a process instance
instance = engine.start_process_instance(
    process_definition_uri="http://example.org/bpmn/myprocess.bpmn",
    initial_variables={
        "customer_name": "John Doe",
        "order_total": 150.00
    }
)

print(f"Started instance: {instance.instance_id}")
print(f"Status: {instance.status}")

# 5. Check instance status
status = engine.get_instance_status(instance.instance_id)
print(f"Current status: {status}")

# 6. Stop the instance (if needed)
engine.stop_process_instance(instance.instance_id, "Demo completion")
```

## Key Classes

### ProcessInstance
Represents a running process instance:
- `instance_id`: Unique identifier
- `status`: Current state (CREATED, RUNNING, SUSPENDED, COMPLETED, TERMINATED)
- `tokens`: List of active tokens in the process
- `created_at/updated_at`: Timestamps

### RDFProcessEngine
Main engine class with methods:
- `start_process_instance()`: Start a new process instance
- `stop_process_instance()`: Stop a running instance
- `get_instance_status()`: Get current instance information
- `list_instances()`: List instances with filtering
- `register_topic_handler()`: Register service task handlers

## Process States

- **CREATED**: Instance created but not yet started
- **RUNNING**: Instance is actively executing
- **SUSPENDED**: Instance execution is paused
- **COMPLETED**: Instance finished successfully
- **TERMINATED**: Instance was stopped manually

## Token-Based Execution

The engine uses a token-based execution model:
1. **Start Events**: Create initial tokens
2. **Sequence Flows**: Move tokens between activities
3. **Gateways**: Route tokens based on conditions
4. **End Events**: Consume tokens and complete instances
5. **Service Tasks**: Execute registered handlers
6. **User Tasks**: Wait for external completion

## Service Task Handlers

Register handlers for automated tasks:

```python
def calculate_tax(context):
    total = float(context.get_variable("order_total"))
    tax = total * 0.10
    context.set_variable("tax_amount", tax)

engine.register_topic_handler("calculate_tax", calculate_tax)
```

Handlers receive a `ProcessContext` with:
- `get_variable(name)`: Retrieve process variables
- `set_variable(name, value)`: Store process variables

## Monitoring and Audit

The engine automatically logs events:
- Instance start/stop
- Activity execution
- Variable changes
- Errors and exceptions

Access audit logs via SPARQL queries on the instance graph.

## Persistence

Basic instance state persistence is implemented:
- Instance metadata stored in RDF
- Token positions tracked
- Variable values maintained
- Audit events logged

## Error Handling

Current implementation includes:
- Exception handling during execution
- Token status management
- Instance termination on errors
- Audit logging of failures

## Next Steps

The engine provides a foundation for:
1. **REST API integration** for external management
2. **User task UI** for manual activities
3. **Timer service** for scheduled events
4. **Message correlation** for external triggers
5. **Advanced persistence** with recovery
6. **Monitoring dashboards** for operations

See `demo_process_engine.py` for complete examples.</content>
<parameter name="filePath">D:\code\spear\PROCESS_ENGINE_README.md