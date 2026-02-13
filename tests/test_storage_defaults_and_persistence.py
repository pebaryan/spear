# Tests for storage defaults and legacy storage persistence behavior.

from rdflib import RDF

from src.api.storage import (
    get_storage,
    reset_storage,
    StorageFacade,
    RDFStorageService,
)
from src.api.storage_service import (
    RDFStorageService as LegacyStorageService,
    PROC,
    INST,
    LOG,
    TASK,
)


def test_legacy_storage_loads_each_graph_from_its_own_file(tmp_path):
    """Regression test for graph-loading bug in RDFStorageService._load_graph."""
    storage1 = LegacyStorageService(storage_path=str(tmp_path))

    def_uri = PROC["def-only"]
    inst_uri = INST["inst-only"]
    audit_uri = LOG["audit-only"]
    task_uri = TASK["task-only"]

    storage1.definitions_graph.add((def_uri, RDF.type, PROC.ProcessDefinition))
    storage1.instances_graph.add((inst_uri, RDF.type, INST.ProcessInstance))
    storage1.audit_graph.add((audit_uri, RDF.type, LOG.Event))
    storage1.tasks_graph.add((task_uri, RDF.type, TASK.UserTask))

    storage1._save_graph(storage1.definitions_graph, "definitions.ttl")
    storage1._save_graph(storage1.instances_graph, "instances.ttl")
    storage1._save_graph(storage1.audit_graph, "audit.ttl")
    storage1._save_graph(storage1.tasks_graph, "tasks.ttl")

    storage2 = LegacyStorageService(storage_path=str(tmp_path))

    assert (def_uri, RDF.type, PROC.ProcessDefinition) in storage2.definitions_graph
    assert (inst_uri, RDF.type, INST.ProcessInstance) in storage2.instances_graph
    assert (audit_uri, RDF.type, LOG.Event) in storage2.audit_graph
    assert (task_uri, RDF.type, TASK.UserTask) in storage2.tasks_graph

    assert (inst_uri, RDF.type, INST.ProcessInstance) not in storage2.definitions_graph
    assert (audit_uri, RDF.type, LOG.Event) not in storage2.definitions_graph
    assert (task_uri, RDF.type, TASK.UserTask) not in storage2.definitions_graph


def test_get_storage_defaults_to_facade(monkeypatch, tmp_path):
    """Storage package should default to facade unless explicitly disabled."""
    monkeypatch.delenv("SPEAR_USE_FACADE", raising=False)
    monkeypatch.setenv("SPEAR_STORAGE_PATH", str(tmp_path))
    reset_storage()

    try:
        storage = get_storage()
        assert isinstance(storage, StorageFacade)
        assert storage.storage_path == str(tmp_path)
    finally:
        reset_storage()


def test_get_storage_can_disable_facade(monkeypatch, tmp_path):
    """Storage package should support explicit opt-out for backward compatibility."""
    monkeypatch.setenv("SPEAR_USE_FACADE", "false")
    monkeypatch.setenv("SPEAR_STORAGE_PATH", str(tmp_path))
    reset_storage()

    try:
        storage = get_storage()
        assert isinstance(storage, RDFStorageService)
        assert storage.storage_path == str(tmp_path)
    finally:
        reset_storage()
