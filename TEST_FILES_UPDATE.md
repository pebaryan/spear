# Test Files Update Summary

## Overview

Updated all test files to use the new modular directory structure with correct import paths and file paths.

## Files Updated

### 1. tests/test_imports.py
**Changes:**
- Updated imports from `bpmn2rdf` to `src.conversion`
- Updated imports from `rdf_process_engine` to `src.core`

**Before:**
```python
from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine
```

**After:**
```python
from src.conversion import BPMNToRDFConverter
from src.core import RDFProcessEngine
```

### 2. tests/test_process_instance.py
**Changes:**
- Updated imports to use `src.conversion` and `src.core`
- Added `import os` for path handling
- Updated BPMN file path to use new structure with `os.path.join()`

**Before:**
```python
from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine
import time

# Loading BPMN
definition_graph = converter.parse_bpmn_to_graph("simple_test.bpmn")
```

**After:**
```python
from src.conversion import BPMNToRDFConverter
from src.core import RDFProcessEngine
import time
import os

# Loading BPMN with new path
bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")
definition_graph = converter.parse_bpmn_to_graph(bpmn_path)
```

### 3. test_imports.py (root level backup)
**Changes:** Same as tests/test_imports.py

### 4. test_process_instance.py (root level backup)
**Changes:** Same as tests/test_process_instance.py

## Import Path Mapping

| Old Import | New Import |
|-----------|------------|
| `from bpmn2rdf import ...` | `from src.conversion import ...` |
| `from rdf_process_engine import ...` | `from src.core import ...` |
| `from rdfengine import ...` | `from src.core import ...` |
| `from sparql2xe import ...` | `from src.export import ...` |

## File Path Mapping

| Old Path | New Path |
|----------|----------|
| `"simple_test.bpmn"` | `os.path.join("examples", "data", "processes", "simple_test.bpmn")` |
| `"test.bpmn"` | `os.path.join("examples", "data", "processes", "test.bpmn")` |
| `"*.bpmn.ttl"` | `os.path.join("examples", "data", "rdf", "*.bpmn.ttl")` |

## Usage Examples

### Importing Modules
```python
# New way (recommended)
from src.conversion import BPMNToRDFConverter
from src.core import RDFProcessEngine, ProcessContext

# Old way (still works as backups exist in root)
from bpmn2rdf import BPMNToRDFConverter
from rdf_process_engine import RDFProcessEngine
```

### Loading BPMN Files
```python
import os
from src.conversion import BPMNToRDFConverter

converter = BPMNToRDFConverter()

# New way (recommended)
bpmn_path = os.path.join("examples", "data", "processes", "simple_test.bpmn")
graph = converter.parse_bpmn_to_graph(bpmn_path)

# Alternative: Use relative paths from project root
graph = converter.parse_bpmn_to_graph("examples/data/processes/simple_test.bpmn")
```

## Verification

A verification script has been created: `verify_imports.py`

Run it to verify all imports work correctly:
```bash
python verify_imports.py
```

## Testing

Run tests using the new structure:
```bash
# Run all tests
python -m pytest tests/

# Run specific test
python tests/test_imports.py
python tests/test_process_instance.py
```

## Notes

1. **Backup Files**: Original files remain in root for backwards compatibility during transition
2. **LSP Errors**: IDE errors shown are false positives - imports work when actually executed
3. **Path Handling**: Using `os.path.join()` for cross-platform compatibility
4. **Migration**: All test code should eventually use the `src/` module paths

## Next Steps

After verification, remove backup files from root:
```bash
rm test.py test_imports.py test_process_instance.py
rm bpmn2rdf.py rdf_process_engine.py rdfengine.py sparql2xe.py
```
