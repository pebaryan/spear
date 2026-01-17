# SPEAR - Semantic Process Engine as RDF
# Core package initialization

from .core import RDFEngine, ProcessContext, RDFProcessEngine, ProcessInstance, Token
from .conversion import BPMNToRDFConverter
from .export import export_to_xes_csv

__all__ = [
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
]

__version__ = "1.0.0"
