# AGENTS.md - Development Guidelines for SPEAR

This document provides comprehensive guidelines for agentic coding assistants working on the SPEAR (Semantic Process Engine as RDF) project.

## Project Overview

SPEAR is a lightweight Python-based BPMN orchestrator that uses RDF (Resource Description Framework) and SPARQL as its core execution language. The project treats business processes as living Knowledge Graphs stored in triplestores.

## Build, Lint, and Test Commands

### Environment Setup
```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Activate virtual environment (Unix/Linux/macOS)
source .venv/bin/activate

# Install dependencies (if requirements.txt exists)
pip install -r requirements.txt
```

### Testing Commands

#### Run All Tests
```bash
# Basic test execution
python -m pytest

# With verbose output
python -m pytest -v

# Run specific test file
python test.py
```

#### Run Single Test Function
```bash
# Run specific test function (when pytest is available)
python -m pytest tests/test_file.py::test_function_name -v

# Run tests in specific module
python -m pytest tests/ -k "test_function_name"
```

### Linting and Code Quality

#### Code Formatting
```bash
# Check code formatting with black (install if needed)
black --check .

# Format code with black
black .

# Check with flake8 (install if needed)
flake8 .

# Check with pylint (install if needed)
pylint rdfengine.py sparql2xe.py
```

#### Type Checking
```bash
# Run mypy for type checking (install if needed)
mypy . --ignore-missing-imports
```

### Build Commands

#### Package Installation
```bash
# Install in development mode (if setup.py exists)
pip install -e .

# Install specific dependencies
pip install rdflib
```

#### Run Application
```bash
# Start the engine (based on README)
python app.py

# Bootstrap process maps
python bootstrap.py
```

## Code Style Guidelines

### Python Standards

#### PEP 8 Compliance
- Follow PEP 8 style guidelines
- Use 4 spaces for indentation (no tabs)
- Limit lines to 88 characters (Black default)
- Use snake_case for function and variable names
- Use CamelCase for class names

#### Imports
```python
# Standard library imports first
import operator
from csv import writer

# Third-party imports second
from rdflib import Graph, Namespace, RDF, Literal, XSD
from rdflib.plugins.stores.sparqlstore import SPARQLStore

# Local imports last
from config import QUERY_ENDPOINT
```

#### Naming Conventions
- **Functions**: snake_case (`get_next_step`, `evaluate_condition`)
- **Classes**: CamelCase (`RDFEngine`, `ProcessContext`)
- **Constants**: UPPER_CASE (`OPERATORS`, `TOPIC_REGISTRY`)
- **Namespaces**: CamelCase with descriptive names (`BPMN`, `PROC`)
- **Variables**: snake_case (`current_node`, `query_string`)

### RDF and SPARQL Patterns

#### Namespace Definitions
```python
# Define namespaces at module level
BPMN = Namespace("http://example.org/bpmn/")
PROC = Namespace("http://example.org/process/")
VAR = Namespace("http://example.org/variables/")
LOG = Namespace("http://example.org/audit/")
```

#### SPARQL Query Formatting
```python
# Multi-line SPARQL queries with proper indentation
query = """
PREFIX log: <http://example.org/audit/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?caseId ?activityLabel ?timestamp
WHERE {
    GRAPH <http://example.org/audit/graph> {
        ?event log:instance ?caseId ;
               log:activity ?activity ;
               log:timestamp ?timestamp .
        OPTIONAL { ?event log:executedBy ?user }
    }
    GRAPH <http://example.org/defs/graph> {
        ?activity rdfs:label ?activityLabel .
    }
}
ORDER BY ?caseId ?timestamp
"""
```

#### RDF Operations
```python
# Adding triples
graph.add((subject_uri, predicate_uri, object_value))

# Querying values
value = graph.value(subject, predicate)

# Removing triples
graph.remove((subject, predicate, None))  # Remove all objects

# Setting values (remove old, add new)
graph.set((subject, predicate, new_value))
```

### Error Handling

#### Exception Patterns
```python
# Raise descriptive exceptions
raise Exception("No valid path found (Dead end)")

# Handle optional values safely
user = str(row.user) if row.user else "System"
```

#### Validation Checks
```python
# Check for None before operations
if condition is None:
    return True  # Default behavior

# Validate query results
if not query_string:
    return True  # Default flow
```

### Function Design

#### Function Signatures
```python
def evaluate_condition(graph, flow_uri, instance_data):
    """Evaluate a condition for a flow transition.

    Args:
        graph: RDF graph containing process definition
        flow_uri: URI of the flow to evaluate
        instance_data: Dictionary of instance variables

    Returns:
        bool: True if condition passes, False otherwise
    """
```

#### Registry Patterns
```python
# Define business logic functions
def tax_calculator(context):
    """Calculate 10% tax on order total."""
    total = float(context.get_variable("orderTotal"))
    tax = total * 0.10
    context.set_variable("taxAmount", tax, datatype=XSD.decimal)
    print(f"Computed tax: {tax} for Instance: {context.inst}")

# Registry mapping topics to functions
TOPIC_REGISTRY = {
    "calculate_tax": tax_calculator,
    "check_inventory": check_inventory_worker,
}
```

### Class Design

#### Context Classes
```python
class ProcessContext:
    """Context for process instance execution."""

    def __init__(self, graph, instance_uri):
        self.g = graph
        self.inst = instance_uri
        self.VAR = Namespace("http://example.org/variables/")

    def set_variable(self, name, value, datatype=None):
        """Set a process variable in the RDF graph."""
        # Remove old value first (variables can change)
        self.g.remove((self.inst, self.VAR[name], None))
        # Add new value
        self.g.add((self.inst, self.VAR[name], Literal(value, datatype=datatype)))

    def get_variable(self, name):
        """Get a process variable from the RDF graph."""
        return self.g.value(self.inst, self.VAR[name])
```

### Testing Patterns

#### Unit Test Structure
```python
# Basic test setup
from rdflib import Graph, Literal, RDF, URIRef, Namespace

# Define test namespaces
PROC = Namespace("http://example.org/process/")
BPMN = Namespace("http://example.org/bpmn/")

def test_simple_process():
    """Test basic process graph creation."""
    g = Graph()

    # Define process elements
    process = PROC.OrderProcess
    task1 = PROC.VerifyPayment

    # Add triples
    g.add((process, RDF.type, BPMN.Process))
    g.add((task1, RDF.type, BPMN.ServiceTask))

    # Assertions
    assert (process, RDF.type, BPMN.Process) in g
    assert (task1, RDF.type, BPMN.ServiceTask) in g
```

### Documentation Standards

#### Module Docstrings
```python
"""
RDF Engine for SPEAR BPMN orchestrator.

This module provides the core execution logic for BPMN processes
stored as RDF graphs, using SPARQL for complex routing decisions.
"""
```

#### Function Docstrings
```python
def execute_step(engine_graph, instance_uri):
    """Execute a single step in a process instance.

    Retrieves the current node for the instance, determines its type,
    and executes the appropriate logic (service task, user task, etc.).
    """
```

### File Organization

#### Module Structure
- `rdfengine.py`: Core engine logic and process execution
- `sparql2xe.py`: Process mining export utilities
- `test.py`: Basic test cases and examples
- `skele.py`: Skeleton/example code for development
- `config.py`: Configuration constants (if exists)

### Security Considerations

#### Input Validation
- Validate URIs and identifiers before using in queries
- Sanitize user inputs used in SPARQL queries
- Use parameterized queries where possible

#### Secrets Management
- Never commit credentials or endpoints to version control
- Use environment variables for sensitive configuration
- Document required environment variables in setup instructions

### Performance Guidelines

#### Query Optimization
- Use specific graph contexts (`GRAPH <uri>`) when possible
- Prefer ASK queries for boolean conditions
- Cache frequently accessed namespace objects

#### Memory Management
- Clean up unused graph objects
- Use streaming for large result sets
- Consider pagination for large queries

### Development Workflow

#### Git Practices
- Write clear commit messages focusing on "why" not "what"
- Use descriptive branch names
- Keep commits focused and atomic

#### Code Review Checklist
- [ ] PEP 8 compliance
- [ ] Type hints where beneficial
- [ ] Docstrings for public functions
- [ ] Unit tests for new functionality
- [ ] RDF operations handle None values safely
- [ ] SPARQL queries are properly formatted
- [ ] Error messages are descriptive

### Dependencies

#### Core Dependencies
- `rdflib`: RDF processing and SPARQL execution
- `pyparsing`: Parser utilities (included with rdflib)

#### Development Dependencies
```bash
pip install black flake8 pylint mypy pytest
```

This document should be updated as the project evolves and new patterns emerge.</content>
<parameter name="filePath">D:\code\spear\AGENTS.md