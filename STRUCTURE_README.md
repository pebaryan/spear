# SPEAR - Semantic Process Engine as RDF

## Project Structure

```
spear/
├── src/                          # Core engine source code
│   ├── __init__.py
│   ├── core/                     # Core RDF engine and process execution
│   │   ├── __init__.py
│   │   ├── rdfengine.py          # RDF engine for process execution
│   │   └── process_engine.py     # Process instance lifecycle management
│   ├── conversion/               # BPMN to RDF conversion
│   │   ├── __init__.py
│   │   └── bpmn2rdf.py           # BPMN XML to RDF Turtle converter
│   ├── export/                   # Export utilities
│   │   ├── __init__.py
│   │   └── sparql2xe.py          # Process mining export (XES format)
│   └── utils/                    # Utility functions
│       ├── __init__.py
│       └── ... (future utilities)
│
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── test.py                   # Basic tests
│   ├── test_imports.py           # Import verification tests
│   └── test_process_instance.py  # Process instance tests
│
├── examples/                     # Examples and demos
│   ├── basic_example.py          # Basic usage example
│   ├── process_demo.py           # Process execution demo
│   └── data/
│       ├── processes/            # Example BPMN process files
│       │   ├── simple_test.bpmn
│       │   └── test.bpmn
│       └── rdf/                  # Example RDF files
│           ├── example.bpmn.ttl
│           ├── flow.bpmn.ttl
│           └── procvar.bpmn.ttl
│
├── docs/                         # Documentation
│   ├── README.md                 # Main documentation
│   ├── AGENTS.md                 # Development guidelines for AI agents
│   ├── TODOS.md                  # Development roadmap
│   └── PROCESS_ENGINE_README.md  # Process engine documentation
│
├── .venv/                        # Python virtual environment
├── .git/                         # Git repository
├── requirements.txt              # Python dependencies (to be created)
└── README.md                     # This file
```

## Quick Start

### Installation
```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install dependencies (when requirements.txt exists)
pip install -r requirements.txt
```

### Basic Usage
```python
from src.conversion import BPMNToRDFConverter
from src.core import RDFProcessEngine

# Convert BPMN to RDF
converter = BPMNToRDFConverter()
definition_graph = converter.parse_bpmn_to_graph("examples/data/processes/simple_test.bpmn")

# Create process engine
engine = RDFProcessEngine(definition_graph)

# Start a process instance
instance = engine.start_process_instance(
    process_definition_uri="http://example.org/bpmn/simple_test.bpmn",
    initial_variables={"customer": "John", "amount": 100}
)
```

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test
python tests/test_process_instance.py
```

## Module Overview

### src.core
- **rdfengine.py**: Core RDF engine with process execution logic
- **process_engine.py**: Process instance lifecycle management (start/stop/monitor)

### src.conversion
- **bpmn2rdf.py**: Converts BPMN 2.0 XML files to RDF Turtle format

### src.export
- **sparql2xe.py**: Exports process logs to XES format for process mining

## Development

### Adding New Features
1. Create module in appropriate `src/` subdirectory
2. Add tests in `tests/`
3. Update documentation in `docs/`
4. Follow guidelines in `docs/AGENTS.md`

### Running Tests
```bash
python -m pytest tests/ -v
```

## Documentation

- **README.md**: Main project documentation
- **docs/AGENTS.md**: Guidelines for AI coding assistants
- **docs/TODOS.md**: Development roadmap and progress
- **docs/PROCESS_ENGINE_README.md**: Process engine usage guide

## License

[Add license information]
