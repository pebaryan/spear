from pytest import fixture, raises
from rdflib import Graph, Namespace, URIRef, XSD
from rdfengine import (
    RDFEngine,
    ProcessContext,
    evaluate_condition,
    resolve_gateway,
    evaluate_sparql_condition,
    tax_calculator,
    check_inventory_worker,
)
import io

BPMN = Namespace("http://example.org/bpmn/")


@fixture
def graph():
    g = Graph()
    return g


@fixture
def rdf_engine(graph):
    return RDFEngine(graph)


@fixture
def process_context(graph):
    return ProcessContext(graph, URIRef("http://example.org/instance1"))


@fixture
def valid_condition_graph():
    g = Graph()
    # Create a condition with variable, operator, and value
    g.add(
        (
            URIRef("http://example.org/condition1"),
            BPMN.variable,
            URIRef("http://example.org/variable1"),
        )
    )
    g.add(
        (
            URIRef("http://example.org/condition1"),
            BPMN.operator,
            URIRef("http://example.org/operator1"),
        )
    )
    g.add(
        (
            URIRef("http://example.org/condition1"),
            BPMN.value,
            URIRef("http://example.org/value1"),
        )
    )
    return g


@fixture
def valid_gateway_graph():
    g = Graph()
    # Create a gateway with two flows
    g.add(
        (
            URIRef("http://example.org/gateway1"),
            BPMN.source,
            URIRef("http://example.org/flow1"),
        )
    )
    g.add(
        (
            URIRef("http://example.org/gateway1"),
            BPMN.target,
            URIRef("http://example.org/target1"),
        )
    )
    g.add(
        (
            URIRef("http://example.org/gateway1"),
            BPMN.source,
            URIRef("http://example.org/flow2"),
        )
    )
    g.add(
        (
            URIRef("http://example.org/gateway1"),
            BPMN.target,
            URIRef("http://example.org/target2"),
        )
    )
    return g


@fixture
def valid_sparql_graph():
    g = Graph()
    # Create a SPARQL condition query
    g.add(
        (
            URIRef("http://example.org/flow1"),
            BPMN.conditionQuery,
            URIRef("http://example.org/query1"),
        )
    )
    return g


@fixture
def valid_tax_context(process_context):
    # Set a variable for tax calculation
    process_context.set_variable("orderTotal", 1000, datatype=XSD.integer)
    return process_context


@fixture
def valid_inventory_context(process_context):
    # Set variables for inventory check
    process_context.set_variable("orderedProduct", "product1", datatype=XSD.string)
    process_context.set_variable("quantityInStock", 50, datatype=XSD.integer)
    return process_context


def test_get_next_step(rdf_engine):
    # Create a graph with a node and next pointer
    g = rdf_engine.g
    node_uri = URIRef("http://example.org/node1")
    next_uri = URIRef("http://example.org/node2")
    g.add((node_uri, BPMN.next, next_uri))

    result = rdf_engine.get_next_step(node_uri)
    assert result == next_uri

    # Test when no next node exists
    result = rdf_engine.get_next_step(URIRef("http://example.org/node3"))
    assert result is None


def test_execute_instance(rdf_engine):
    # Create a simple process with two nodes
    g = rdf_engine.g
    node1 = URIRef("http://example.org/node1")
    node2 = URIRef("http://example.org/node2")
    node3 = URIRef("http://example.org/node3")
    g.add((node1, BPMN.next, node2))
    g.add((node2, BPMN.next, node3))
    g.add((node3, BPMN.next, URIRef("http://example.org/end")))

    rdf_engine.execute_instance(node1)
    # Verify execution path
    assert node1 in g
    assert node2 in g
    assert node3 in g

    # Test when next node is None
    rdf_engine.execute_instance(URIRef("http://example.org/end"))
    assert "Process Finished." in [line for line in g if "Process Finished." in line]


def test_set_variable(process_context):
    process_context.set_variable("testVar", "testValue")
    assert process_context.g.value(process_context.inst, process_context.VAR["testVar"])
    # Test overwriting
    process_context.set_variable("testVar", "newValue")
    assert process_context.g.value(process_context.inst, process_context.VAR["testVar"])


def test_get_variable(process_context):
    process_context.set_variable("testVar", "testValue")
    assert process_context.get_variable("testVar") == "testValue"
    assert process_context.get_variable("missingVar") is None


def test_evaluate_condition(valid_condition_graph):
    # Test greater than condition
    valid_condition_graph.add((URIRef("http://example.org/value1"), XSD.integer, 1500))
    assert evaluate_condition(
        valid_condition_graph, URIRef("http://example.org/flow1"), {"variable1": 1000}
    )
    # Test less than or equal
    valid_condition_graph.add((URIRef("http://example.org/value1"), XSD.integer, 500))
    assert evaluate_condition(
        valid_condition_graph, URIRef("http://example.org/flow1"), {"variable1": 400}
    )
    # Test equality
    valid_condition_graph.add((URIRef("http://example.org/value1"), XSD.integer, 1000))
    assert evaluate_condition(
        valid_condition_graph, URIRef("http://example.org/flow1"), {"variable1": 1000}
    )


def test_resolve_gateway(valid_gateway_graph):
    # Test condition evaluation
    valid_gateway_graph.add(
        (
            URIRef("http://example.org/flow1"),
            BPMN.condition,
            URIRef("http://example.org/condition1"),
        )
    )
    valid_gateway_graph.add(
        (
            URIRef("http://example.org/flow2"),
            BPMN.condition,
            URIRef("http://example.org/condition2"),
        )
    )
    # Assume condition1 is true, condition2 is false
    assert resolve_gateway(
        valid_gateway_graph, URIRef("http://example.org/gateway1"), {"variable1": 1000}
    ) == URIRef("http://example.org/target1")
    # Test dead end
    with raises(Exception):
        resolve_gateway(
            valid_gateway_graph,
            URIRef("http://example.org/gateway1"),
            {"variable1": 500},
        )


def test_evaluate_sparql_condition(valid_sparql_graph):
    # Test condition query
    valid_sparql_graph.add(
        (
            URIRef("http://example.org/query1"),
            XSD.string,
            "SELECT ?x WHERE { ?instance var:variable ?x }",
        )
    )
    assert evaluate_sparql_condition(
        valid_sparql_graph,
        URIRef("http://example.org/flow1"),
        URIRef("http://example.org/instance1"),
    )


def test_tax_calculator(valid_tax_context):
    tax_calculator(valid_tax_context)
    assert valid_tax_context.get_variable("taxAmount") == 100.0


def test_check_inventory_worker(valid_inventory_context):
    check_inventory_worker(valid_inventory_context)
    # Verify query execution
    assert (
        valid_inventory_context.g.value(
            valid_inventory_context.inst, URIRef("http://example.org/stock")
        )
        == 50
    )
