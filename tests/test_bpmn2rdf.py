import pytest
from pytest import fixture, raises, raises, raises
from rdflib import Graph, Namespace, URIRef, XSD
from bpmn2rdf import BPMNToRDFConverter
import xml.etree.ElementTree as ET
import io


@fixture
def converter():
    return BPMNToRDFConverter()


@fixture
def valid_bpmn():
    return """
<process id="proc1">
  <startEvent id="start1" name="Start"/>
  <sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
  <task id="task1" name="Task 1"/>
</process>
"""


@fixture
def invalid_bpmn():
    return """
<process id="proc1">
  <startEvent id="start1" name="Start"/>
  <sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
  <task id="task1" name="Task 1"/>
"""


def test_parse_bpmn(converter, valid_bpmn):
    output = converter.parse_bpmn(io.StringIO(valid_bpmn))
    assert "rdf:type bpmn:process" in output
    assert "rdf:type bpmn:startEvent" in output
    assert "rdf:type bpmn:task" in output


def test_parse_bpmn_to_graph(converter, valid_bpmn):
    graph = converter.parse_bpmn_to_graph(io.StringIO(valid_bpmn))
    assert len(graph) > 0
    triples = list(graph)
    assert len(triples) >= 3
    # Check that all expected triples are present by checking for specific URIs
    subjects = [str(t[0]) for t in triples]
    predicates = [str(t[1]) for t in triples]
    objects = [str(t[2]) for t in triples]

    # Check that process, startEvent, and task types exist
    assert "http://example.org/bpmn/proc1" in subjects
    assert "http://example.org/bpmn/start1" in subjects
    assert "http://example.org/bpmn/task1" in subjects
    assert "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" in predicates
    assert "http://dkm.fbk.eu/index.php/BPMN2_Ontology#process" in objects
    assert "http://dkm.fbk.eu/index.php/BPMN2_Ontology#startEvent" in objects
    assert "http://dkm.fbk.eu/index.php/BPMN2_Ontology#task" in objects


def test_missing_id(converter):
    element = ET.fromstring('<startEvent name="Start"/>')
    converter._process_element(element, None)
    # Check that a startEvent triple was created with a generated ID
    assert any(
        "startEvent" in triple and "rdf:type bpmn:startEvent" in triple
        for triple in converter.triples
    )


def test_invalid_xml(converter):
    with pytest.raises(ET.ParseError):
        converter.parse_bpmn(io.StringIO("invalid xml"))
