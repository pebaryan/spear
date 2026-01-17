# SPEAR Package Structure - Complete Guide

## Overview

The SPEAR project uses a proper Python package structure with explicit exports in `__init__.py` files for clean and predictable imports.

## Package Structure

```
src/
├── __init__.py              # Main package exports
├── core/                    # Core engine modules
│   ├── __init__.py          # Core package exports
│   ├── rdfengine.py         # RDF engine with process execution
│   └── process_engine.py    # Process instance management
├── conversion/              # Data conversion modules
│   ├── __init__.py          # Conversion package exports
│   └── bpmn2rdf.py          # BPMN XML to RDF converter
├── export/                  # Export utilities
│   ├── __init__.py          # Export package exports
│   └── sparql2xe.py         # Process mining export
└── utils/                   # Utility functions
    └── __init__.py
```

## Importing Modules

### Method 1: Import from top-level package (Recommended)
```python
from src import (
    BPMNToRDFConverter,
    RDFProcessEngine,
    ProcessInstance,
    Token,
    ProcessContext,
    RDFEngine,
    export_to_xes_csv
)

# Usage
converter = BPMNToRDFConverter()
engine = RDFProcessEngine(graph)
```

### Method 2: Import from specific subpackages
```python
# Core engine
from src.core import RDFEngine, ProcessContext
from src.core import RDFProcessEngine, ProcessInstance, Token

# Conversion
from src.conversion import BPMNToRDFConverter

# Export
from src.export import export_to_xes_csv
```

### Method 3: Import directly from modules (Not Recommended)
```python
# Works but bypasses package exports
from src.core.rdfengine import RDFEngine
from src.conversion.bpmn2rdf import BPMNToRDFConverter
```

## Available Exports

### src Package (Top-Level)
```python
from src import (
    # Core engine
    'RDFEngine',
    'ProcessContext',
    'RDFProcessEngine',
    'ProcessInstance',
    'Token',
    # Conversion
    'BPMNToRDFConverter',
    # Export
    'export_to_xes_csv'
)
```

### src.core Package
```python
from src.core import (
    'RDFEngine',
    'ProcessContext',
    'RDFProcessEngine',
    'ProcessInstance',
    'Token'
)
```

### src.conversion Package
```python
from src.conversion import (
    'BPMNToRDFConverter'
)
```

### src.export Package
```python
from src.export import (
    'export_to_xes_csv'
)
```

## Class and Function Reference

### Core Engine Classes (src.core)

#### RDFEngine
```python
from src import RDFEngine

engine = RDFEngine(graph)
```

**Methods:**
- `get_next_step(current_node_uri)` - Get next node in process
- `execute_instance(start_node)` - Execute a process instance

#### ProcessContext
```python
from src import ProcessContext

context = ProcessContext(graph, instance_uri)
context.set_variable(name, value)
context.get_variable(name)
```

#### RDFProcessEngine
```python
from src import RDFProcessEngine

engine = RDFProcessEngine(definition_graph, instance_graph=None)
engine.start_process_instance(process_uri, initial_variables, start_event_id)
engine.stop_process_instance(instance_id, reason)
engine.get_instance_status(instance_id)
engine.list_instances(process_uri, status)
```

#### ProcessInstance
```python
from src import ProcessInstance

instance = ProcessInstance(process_definition_uri, instance_id=None)
# Properties:
# - instance_id
# - instance_uri
# - process_definition_uri
# - status (CREATED, RUNNING, SUSPENDED, COMPLETED, TERMINATED)
# - tokens
# - created_at
# - updated_at
```

#### Token
```python
from src import Token

token = Token(token_id=None)
# Methods:
# - move_to_node(node_uri)
# Properties:
# - token_id
# - token_uri
# - current_node
# - status (ACTIVE, WAITING, CONSUMED)
```

### Conversion Classes (src.conversion)

#### BPMNToRDFConverter
```python
from src import BPMNToRDFConverter

converter = BPMNToRDFConverter()
turtle_output = converter.parse_bpmn(file_path)
graph = converter.parse_bpmn_to_graph(file_path)
```

**Methods:**
- `parse_bpmn(file_path)` - Convert BPMN XML to Turtle string
- `parse_bpmn_to_graph(file_path)` - Convert BPMN XML to rdflib.Graph

### Export Functions (src.export)

#### export_to_xes_csv
```python
from src import export_to_xes_csv

export_to_xes_csv(output_file="process_logs.csv")
```

## Complete Usage Example

```python
#!/usr/bin/env python3
"""
Complete example of using SPEAR with the new package structure
"""

import os
from src import (
    BPMNToRDFConverter,
    RDFProcessEngine,
    ProcessInstance,
    Token
)

# 1. Load BPMN process definition
converter = BPMNToRDFConverter()
bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")
definition_graph = converter.parse_bpmn_to_graph(bpmn_path)
print(f"Loaded {len(definition_graph)} triples")

# 2. Create process engine
engine = RDFProcessEngine(definition_graph)

# 3. Register service task handlers
def process_order(context):
    customer = context.get_variable("customer_name")
    total = context.get_variable("order_total")
    print(f"Processing order for {customer}: ${total}")

engine.register_topic_handler("process_order", process_order)

# 4. Start a process instance
instance = engine.start_process_instance(
    process_definition_uri="http://example.org/bpmn/simple_test.bpmn",
    initial_variables={
        "customer_name": "John Doe",
        "order_total": 150.00
    }
)
print(f"Started instance: {instance.instance_id}")

# 5. Monitor execution
status = engine.get_instance_status(instance.instance_id)
print(f"Status: {status['status']}")
print(f"Tokens: {status['token_count']}")

# 6. Stop instance if needed
engine.stop_process_instance(instance.instance_id, "Demo complete")
```

## Best Practices

1. **Use top-level imports** for cleaner code:
   ```python
   from src import BPMNToRDFConverter, RDFProcessEngine
   ```

2. **Use `os.path.join()`** for cross-platform file paths:
   ```python
   bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")
   ```

3. **Import what you need** - don't import entire modules unnecessarily

4. **Use the package exports** defined in `__init__.py` for better IDE support

## Testing

Run the verification script to confirm imports work:
```bash
python verify_package.py
```

Run tests:
```bash
python -m pytest tests/
python tests/test_imports.py
python tests/test_process_instance.py
```

## Notes

- All `__init__.py` files include `__all__` for explicit API definition
- IDE autocomplete works properly with explicit exports
- Imports work from any location in the project
- Package structure follows Python packaging best practices
