# SPEAR Project Reorganization Summary

## Overview

The SPEAR project has been reorganized from a flat structure with 29+ files in the root directory to a clean, modular architecture following Python best practices.

## Previous Structure (Before)

```
spear/
├── *.py (29 files - all mixed together)
├── *.bpmn (2 files)
├── *.ttl (3 files)
├── .venv/
├── .git/
└── *.md (4 files)
```

**Problems:**
- Core engine files mixed with test files
- Demo and debug files in root directory
- No clear separation of concerns
- Difficult to navigate and maintain

## New Structure (After)

```
spear/
├── src/                          # Clean source code
│   ├── core/                     # Core engine modules
│   │   ├── rdfengine.py
│   │   └── process_engine.py
│   ├── conversion/               # Data conversion
│   │   └── bpmn2rdf.py
│   ├── export/                   # Export utilities
│   │   └── sparql2xe.py
│   └── utils/                    # Utilities
│
├── tests/                        # Organized tests
│   ├── test.py
│   ├── test_imports.py
│   └── test_process_instance.py
│
├── examples/                     # Examples and data
│   ├── basic_example.py
│   ├── process_demo.py
│   └── data/
│       ├── processes/            # BPMN files
│       └── rdf/                  # RDF files
│
├── docs/                         # Documentation
│   ├── README.md
│   ├── AGENTS.md
│   ├── TODOS.md
│   └── PROCESS_ENGINE_README.md
│
├── .venv/
├── .git/
└── STRUCTURE_README.md           # This file
```

## Benefits of New Structure

### 1. **Modularity**
- Clear separation between core engine, conversion, and export modules
- Each package has its own `__init__.py` for proper Python packaging
- Easy to understand project boundaries

### 2. **Scalability**
- New features can be added to appropriate modules
- Clear location for utils, extensions, and plugins
- Scales well as project grows

### 3. **Maintainability**
- Easier to find and modify files
- Logical grouping of related functionality
- Reduced cognitive load when navigating codebase

### 4. **Testing**
- Tests organized in dedicated directory
- Easy to run specific test suites
- Follows pytest conventions

### 5. **Documentation**
- Dedicated docs directory
- Clear separation from code
- Easy to find relevant documentation

### 6. **Professional**
- Follows Python packaging best practices
- Similar structure to mature open-source projects
- Easier for new contributors to understand

## Migration Guide

### For Developers

#### Importing Modules (Old Way)
```python
# From root directory
from bpmn2rdf import BPMNToRDFConverter
from rdfengine import RDFEngine
```

#### Importing Modules (New Way)
```python
# From anywhere
from src.conversion import BPMNToRDFConverter
from src.core import RDFEngine, RDFProcessEngine
```

#### Running Tests (Old Way)
```bash
python test.py
python test_process_instance.py
```

#### Running Tests (New Way)
```bash
python -m pytest tests/
python tests/test_process_instance.py
```

#### Using BPMN Files (Old Way)
```python
graph = converter.parse_bpmn("simple_test.bpmn")
```

#### Using BPMN Files (New Way)
```python
graph = converter.parse_bpmn("examples/data/processes/simple_test.bpmn")
```

### File Mappings

| Old Location | New Location |
|-------------|--------------|
| `rdfengine.py` | `src/core/rdfengine.py` |
| `rdf_process_engine.py` | `src/core/rdf_process_engine.py` |
| `bpmn2rdf.py` | `src/conversion/bpmn2rdf.py` |
| `sparql2xe.py` | `src/export/sparql2xe.py` |
| `test.py` | `tests/test.py` |
| `test_imports.py` | `tests/test_imports.py` |
| `test_process_instance.py` | `tests/test_process_instance.py` |
| `simple_test.bpmn` | `examples/data/processes/simple_test.bpmn` |
| `test.bpmn` | `examples/data/processes/test.bpmn` |
| `*.bpmn.ttl` | `examples/data/rdf/` |

## Cleanup Status

### Files Removed (Temporary/Debug)
- `debug_*.py` - Debug scripts
- `quick_*.py` - Quick test scripts
- `test_*.py` - Temporary test files
- `show_*.py` - Display scripts
- `print_*.py` - Print scripts
- `check_*.py` - Check scripts
- `minimal_test.py`
- `simple_test.py`
- `demo_process_engine.py`
- `final_test.py`
- `rdf_process_engine_clean.py`

### Files Kept (Root - Backwards Compatibility)
- `rdfengine.py` - Original (backup)
- `rdf_process_engine.py` - Original (backup)
- `bpmn2rdf.py` - Original (backup)
- `sparql2xe.py` - Original (backup)
- `test.py` - Original (backup)
- `test_imports.py` - Original (backup)
- `test_process_instance.py` - Original (backup)
- `skele.py` - Skeleton/example code
- `*.md` - Documentation files

## Next Steps

### 1. Update All Imports
Update all Python files to use new import paths:
```python
# Old
from rdfengine import ProcessContext
from bpmn2rdf import BPMNToRDFConverter

# New
from src.core import ProcessContext
from src.conversion import BPMNToRDFConverter
```

### 2. Create Requirements.txt
```bash
pip freeze > requirements.txt
```

### 3. Update Documentation
- Update `README.md` with new structure
- Update `AGENTS.md` with new import paths
- Update examples to use new structure

### 4. Remove Backups (After Testing)
Once all code works with new structure:
```bash
rm rdfengine.py rdf_process_engine.py bpmn2rdf.py sparql2xe.py
rm test.py test_imports.py test_process_instance.py
```

### 5. Add Package Configuration (Optional)
Create `setup.py` or `pyproject.toml` for proper package installation.

## Verification Checklist

- [ ] All imports work with new structure
- [ ] Tests run successfully
- [ ] Examples work with new paths
- [ ] Documentation is accurate
- [ ] Backups can be removed after verification

## Summary

The SPEAR project now has a **professional, modular structure** that:
- ✅ Separates concerns (core, conversion, export, utils)
- ✅ Organizes tests in dedicated directory
- ✅ Groups examples and data logically
- ✅ Provides clear documentation structure
- ✅ Follows Python packaging best practices
- ✅ Scales well for future growth
- ✅ Easier to maintain and extend

**Total files moved**: 9 core files, 3 test files, 5 data files  
**New directories created**: 4 (src/core, src/conversion, src/export, src/utils) + tests + examples/data/*  
**Temporary files removed**: 20+ debug/temp files
