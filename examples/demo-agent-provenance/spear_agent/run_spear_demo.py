"""Run BPMN-modeled demo agent with SPEAR engine and emit RDF logs."""
import os
import sys
from pathlib import Path
from rdflib import Graph, Namespace, RDF

SPEAR_ROOT = Path('/mnt/vmware/home/peb/works/hacks/spear')
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # demo-agent-provenance
for p in (SPEAR_ROOT, PROJECT_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from src.conversion.bpmn2rdf import BPMNToRDFConverter
from src.core import RDFProcessEngine
from spear_agent.handlers import (
    handle_run_tests,
    handle_blocked_cmd,
    handle_apply_fix,
    reset_demo_fixture,
)

BASE = Path(__file__).resolve().parent
PROCESS_DIR = BASE / 'processes'
ENGINE_GRAPH_PATH = BASE / 'engine_graph.ttl'
MEMORY_GRAPH_PATH = BASE / 'memory_graph.ttl'
OUTPUT_PROV_PATH = BASE / 'spear-demo-prov.ttl'

BPMN_NS = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
CAMUNDA_NS = Namespace("http://camunda.org/schema/1.0/bpmn#")
AG_NS = Namespace("http://example.org/agent#")


def load_graph(path: Path) -> Graph:
    g = Graph()
    if path.exists():
        g.parse(path, format='turtle')
    return g


def merge_bpmn(engine_graph: Graph):
    engine_graph.bind("bpmn", BPMN_NS, replace=True)
    engine_graph.bind("camunda", CAMUNDA_NS, replace=True)
    # Clear old BPMN triples
    for s in list(engine_graph.subjects()):
        if str(s).startswith("http://example.org/bpmn/"):
            for p, o in list(engine_graph.predicate_objects(s)):
                engine_graph.remove((s, p, o))
    converter = BPMNToRDFConverter()
    for path in PROCESS_DIR.glob('*.bpmn'):
        bpmn_graph = converter.parse_bpmn_to_graph(str(path))
        for triple in bpmn_graph:
            engine_graph.add(triple)
    # mirror camunda:topic to bpmn:topic
    for subject, _, topic in list(engine_graph.triples((None, CAMUNDA_NS.topic, None))):
        engine_graph.add((subject, BPMN_NS.topic, topic))
    # normalize lowercase element types to expected uppercase
    type_map = {
        "startEvent": "StartEvent",
        "endEvent": "EndEvent",
        "serviceTask": "ServiceTask",
        "userTask": "UserTask",
        "exclusiveGateway": "ExclusiveGateway",
        "parallelGateway": "ParallelGateway",
    }
    for lower, upper in type_map.items():
        lower_uri = BPMN_NS[lower]
        upper_uri = BPMN_NS[upper]
        for subject, _, _ in list(engine_graph.triples((None, RDF.type, lower_uri))):
            engine_graph.remove((subject, RDF.type, lower_uri))
            engine_graph.add((subject, RDF.type, upper_uri))


def clear_agent_actions(engine_graph: Graph):
    # Keep BPMN/audit history, but clear action-level demo nodes for deterministic query output.
    to_remove = []
    for subject in set(engine_graph.subjects(RDF.type, AG_NS.Action)):
        to_remove.append(subject)
    for subject in list(engine_graph.subjects()):
        if str(subject).startswith("http://example.org/agent/action/"):
            to_remove.append(subject)
    for subject in set(to_remove):
        for p, o in list(engine_graph.predicate_objects(subject)):
            engine_graph.remove((subject, p, o))


def main():
    engine_graph = load_graph(ENGINE_GRAPH_PATH)
    memory_graph = load_graph(MEMORY_GRAPH_PATH)
    merge_bpmn(engine_graph)
    clear_agent_actions(engine_graph)
    reset_demo_fixture()

    engine = RDFProcessEngine(engine_graph, engine_graph)
    engine.register_topic_handler('run_tests', handle_run_tests)
    engine.register_topic_handler('blocked_cmd', handle_blocked_cmd)
    engine.register_topic_handler('apply_fix', handle_apply_fix)

    process_uri = "http://example.org/bpmn/AgentDemoProcess"
    instance = engine.start_process_instance(process_uri)

    # Save graphs
    engine_graph.serialize(ENGINE_GRAPH_PATH, format='turtle')
    memory_graph.serialize(MEMORY_GRAPH_PATH, format='turtle')
    engine_graph.serialize(OUTPUT_PROV_PATH, format='turtle')

    print(f"Process instance status: {instance.status}")
    print(f"Run URI: {instance.instance_uri}")
    print(f"Provenance saved: {OUTPUT_PROV_PATH}")


if __name__ == '__main__':
    main()
