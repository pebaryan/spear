from rdflib import Graph, Namespace, URIRef

from src.core.gateways import GatewayEvaluator


BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")


def test_gateway_sparql_condition_uses_instance_variables():
    def_graph = Graph()
    inst_graph = Graph()
    evaluator = GatewayEvaluator(def_graph, inst_graph)

    query = """
    PREFIX var: <http://example.org/variables/>
    ASK {
        ?instance var:amount ?amount .
        FILTER(?amount > 10)
    }
    """
    instance_uri = URIRef("http://example.org/instance/test-1")

    assert evaluator._evaluate_sparql_condition(
        query,
        {"amount": 15},
        instance_uri,
    )
    assert not evaluator._evaluate_sparql_condition(
        query,
        {"amount": 5},
        instance_uri,
    )

