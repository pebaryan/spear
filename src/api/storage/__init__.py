# Storage Package for SPEAR Engine
# Provides RDF-based persistence for process definitions, instances, and tasks

import os
from typing import Union

# Re-export from the original storage service for backward compatibility
from src.api.storage_service import RDFStorageService

# New modular components
from .base import (
    BaseStorageService,
    BPMN,
    PROC,
    INST,
    VAR,
    LOG,
    META,
    TASK,
)

from .audit_repository import AuditRepository
from .variables import VariablesService
from .process_repository import ProcessRepository
from .task_repository import TaskRepository
from .instance_repository import InstanceRepository
from .facade import StorageFacade, get_facade, reset_facade

# Shared storage instance
_shared_storage: Union[RDFStorageService, StorageFacade, None] = None


def get_storage() -> Union[RDFStorageService, StorageFacade]:
    """
    Get or create the shared storage service instance.

    Defaults to StorageFacade unless SPEAR_USE_FACADE is explicitly set to false.
    Uses SPEAR_STORAGE_PATH to select where RDF files are persisted.
    """
    global _shared_storage
    if _shared_storage is None:
        use_facade = os.environ.get("SPEAR_USE_FACADE", "true").lower() != "false"
        storage_path = os.environ.get("SPEAR_STORAGE_PATH", "data/spear_rdf")
        if use_facade:
            _shared_storage = get_facade(storage_path)
        else:
            _shared_storage = RDFStorageService(storage_path=storage_path)
    return _shared_storage


def reset_storage() -> None:
    """Reset the shared storage instance (useful for testing)."""
    global _shared_storage
    _shared_storage = None
    reset_facade()


__all__ = [
    # Backward compatibility exports
    "RDFStorageService",
    "get_storage",
    "reset_storage",
    # New base storage
    "BaseStorageService",
    # New repositories/services
    "AuditRepository",
    "VariablesService",
    "ProcessRepository",
    "TaskRepository",
    "InstanceRepository",
    # New facade
    "StorageFacade",
    "get_facade",
    "reset_facade",
    # Namespaces
    "BPMN",
    "PROC",
    "INST",
    "VAR",
    "LOG",
    "META",
    "TASK",
]
