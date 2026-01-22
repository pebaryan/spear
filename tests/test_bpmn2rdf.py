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
    assert list(graph)[:3] == [
        (
            "<http://example.org/bpmn/proc1>",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "http://dkm.fbk.eu/index.php/BPMN2_Ontology#process",
        ),
        (
            "<http://example.org/bpmn/start1>",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "http://dkm.fbk.eu/index.php/BPMN2_Ontology#startEvent",
        ),
        (
            "<http://example.org/bpmn/task1>",
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
            "http://dkm.fbk.eu/index.php/BPMN2_Ontology#task",
        ),
    ]


def test_missing_id(converter):
    element = ET.fromstring('<startEvent name="Start"/>')
    converter._process_element(element, None)
    assert "<http://example.org/bpmn/start1>" in converter.triples


def test_invalid_xml(converter):
    with pytest.raises(ET.ParseError):
        converter.parse_bpmn(io.StringIO("invalid xml"))
