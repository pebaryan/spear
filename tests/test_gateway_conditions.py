#!/usr/bin/env python3
"""
Gateway condition evaluation tests
Tests exclusive and parallel gateway support with condition evaluation
"""

import pytest
from rdflib import Graph, Namespace, URIRef, Literal, XSD
import tempfile
import io


class TestGatewayConditionConversion:
    """Test BPMN to RDF conversion for gateway conditions"""

    @pytest.fixture
    def converter(self):
        from src.conversion.bpmn2rdf import BPMNToRDFConverter

        return BPMNToRDFConverter()

    def test_exclusive_gateway_with_camunda_expression(self, converter):
        """Test parsing exclusive gateway with camunda:expression condition"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <bpmn:process id="testProc">
                <bpmn:startEvent id="start1"/>
                <bpmn:exclusiveGateway id="gateway1"/>
                <bpmn:endEvent id="endApprove"/>
                <bpmn:endEvent id="endReject"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flowApprove" sourceRef="gateway1" targetRef="endApprove">
                    <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${approved == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowReject" sourceRef="gateway1" targetRef="endReject">
                    <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${approved == false}"/>
                </bpmn:sequenceFlow>
            </bpmn:process>
        </bpmn:definitions>"""

        result = converter.parse_bpmn(io.StringIO(bpmn))

        # Check that condition queries are generated
        assert "bpmn:conditionQuery" in result
        assert "ASK" in result
        assert "approved" in result

    def test_exclusive_gateway_with_numeric_condition(self, converter):
        """Test parsing gateway with numeric comparison"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <bpmn:process id="testProc">
                <bpmn:startEvent id="start1"/>
                <bpmn:exclusiveGateway id="gateway1"/>
                <bpmn:serviceTask id="task1"/>
                <bpmn:serviceTask id="task2"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="gateway1" targetRef="task1">
                    <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${amount gt 1000}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flow3" sourceRef="gateway1" targetRef="task2">
                    <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${amount lte 1000}"/>
                </bpmn:sequenceFlow>
            </bpmn:process>
        </bpmn:definitions>"""

        result = converter.parse_bpmn(io.StringIO(bpmn))

        # Should have condition queries for both flows
        assert result.count("bpmn:conditionQuery") >= 2
        assert "amount" in result

    def test_gateway_with_default_flow(self, converter):
        """Test parsing gateway with default flow"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
            <bpmn:process id="testProc">
                <bpmn:startEvent id="start1"/>
                <bpmn:exclusiveGateway id="gateway1" camunda:default="flowDefault"/>
                <bpmn:serviceTask id="task1"/>
                <bpmn:serviceTask id="task2"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flowSpecial" sourceRef="gateway1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flowDefault" sourceRef="gateway1" targetRef="task2"/>
            </bpmn:process>
        </bpmn:definitions>"""

        result = converter.parse_bpmn(io.StringIO(bpmn))

        # Should have default attribute (stored as camunda:default)
        assert "camunda:default" in result or "bpmn:default" in result
        assert "flowDefault" in result

    def test_gateway_condition_with_different_types(self, converter):
        """Test parsing conditions with different expression types"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <bpmn:process id="testProc">
                <bpmn:startEvent id="start1"/>
                <bpmn:exclusiveGateway id="gateway1"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="gateway1" targetRef="end1">
                    <bpmn:conditionExpression xsi:type="tFormalExpression">true</bpmn:conditionExpression>
                </bpmn:sequenceFlow>
            </bpmn:process>
        </bpmn:definitions>"""

        result = converter.parse_bpmn(io.StringIO(bpmn))

        # Should store condition type and body
        assert "bpmn:conditionType" in result or "bpmn:conditionBody" in result


class TestGatewayConditionEvaluation:
    """Test condition evaluation during execution"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_evaluate_gateway_condition_approved_true(self, storage):
        """Test exclusive gateway with approved=true condition"""
        process_id = storage.deploy_process(
            name="Approval Process",
            description="Test approval routing",
            bpmn_content="""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                              xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <bpmn:process id="approvalProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:exclusiveGateway id="gateway1"/>
                    <bpmn:endEvent id="endApprove"/>
                    <bpmn:endEvent id="endReject"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                    <bpmn:sequenceFlow id="flowApprove" sourceRef="gateway1" targetRef="endApprove">
                        <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${approved == true}"/>
                    </bpmn:sequenceFlow>
                    <bpmn:sequenceFlow id="flowReject" sourceRef="gateway1" targetRef="endReject">
                        <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${approved == false}"/>
                    </bpmn:sequenceFlow>
                </bpmn:process>
            </bpmn:definitions>""",
        )

        # Create instance with approved=true
        result = storage.create_instance(
            process_id=process_id, variables={"approved": "true"}
        )

        instance_id = result["id"]

        # Check that instance was created successfully
        instance = storage.get_instance(instance_id)
        assert instance is not None
        print(f"Instance {instance_id} created with status: {instance['status']}")

        # Test condition evaluation directly
        gateway_uri = URIRef("http://example.org/bpmn/gateway1")
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        next_node = storage._evaluate_gateway_conditions(instance_uri, gateway_uri)
        assert next_node is not None
        assert "endApprove" in str(next_node)
        print(f"Gateway routed to: {next_node}")

    def test_evaluate_gateway_condition_numeric(self, storage):
        """Test gateway with numeric condition"""
        process_id = storage.deploy_process(
            name="Credit Check Process",
            description="Test credit amount routing",
            bpmn_content="""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                              xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <bpmn:process id="creditProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:exclusiveGateway id="gateway1"/>
                    <bpmn:endEvent id="endHighRisk"/>
                    <bpmn:endEvent id="endLowRisk"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                    <bpmn:sequenceFlow id="flowHigh" sourceRef="gateway1" targetRef="endHighRisk">
                        <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${creditScore lt 600}"/>
                    </bpmn:sequenceFlow>
                    <bpmn:sequenceFlow id="flowLow" sourceRef="gateway1" targetRef="endLowRisk">
                        <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${creditScore gte 600}"/>
                    </bpmn:sequenceFlow>
                </bpmn:process>
            </bpmn:definitions>""",
        )

        # Test with high credit score
        result = storage.create_instance(
            process_id=process_id, variables={"creditScore": "750"}
        )

        instance_id = result["id"]
        gateway_uri = URIRef("http://example.org/bpmn/gateway1")
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        next_node = storage._evaluate_gateway_conditions(instance_uri, gateway_uri)
        assert next_node is not None
        assert "endLowRisk" in str(next_node)
        print(f"Instance with creditScore=750 routed to: {next_node}")

        # Test with low credit score
        result2 = storage.create_instance(
            process_id=process_id, variables={"creditScore": "550"}
        )

        instance_id2 = result2["id"]
        instance_uri2 = URIRef(f"http://example.org/instance/{instance_id2}")

        next_node2 = storage._evaluate_gateway_conditions(instance_uri2, gateway_uri)
        assert next_node2 is not None
        assert "endHighRisk" in str(next_node2)
        print(f"Instance with creditScore=550 routed to: {next_node2}")

    def test_gateway_condition_with_service_task(self, storage):
        """Test gateway routing to service tasks based on condition"""
        process_id = storage.deploy_process(
            name="Order Processing",
            description="Route to appropriate handler",
            bpmn_content="""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                              xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                              xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                <bpmn:process id="orderProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:exclusiveGateway id="gateway1"/>
                    <bpmn:serviceTask id="taskExpress" name="Express Shipping" camunda:topic="express_handler"/>
                    <bpmn:serviceTask id="taskStandard" name="Standard Shipping" camunda:topic="standard_handler"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
                    <bpmn:sequenceFlow id="flowExpress" sourceRef="gateway1" targetRef="taskExpress">
                        <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${shipping eq express}"/>
                    </bpmn:sequenceFlow>
                    <bpmn:sequenceFlow id="flowStandard" sourceRef="gateway1" targetRef="taskStandard">
                        <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${shipping eq standard}"/>
                    </bpmn:sequenceFlow>
                    <bpmn:sequenceFlow id="flowEnd" sourceRef="taskExpress" targetRef="end1"/>
                    <bpmn:sequenceFlow id="flowEnd2" sourceRef="taskStandard" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>""",
        )

        # Register handlers to track execution
        called_handler = []

        def express_handler(instance_id, variables):
            called_handler.append("express")
            return variables

        def standard_handler(instance_id, variables):
            called_handler.append("standard")
            return variables

        storage.register_topic_handler("express_handler", express_handler)
        storage.register_topic_handler("standard_handler", standard_handler)

        # Test with express shipping
        result = storage.create_instance(
            process_id=process_id, variables={"shipping": "express"}
        )

        instance_id = result["id"]
        gateway_uri = URIRef("http://example.org/bpmn/gateway1")
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        next_node = storage._evaluate_gateway_conditions(instance_uri, gateway_uri)
        assert next_node is not None
        assert "taskExpress" in str(next_node)
        print(f"Express shipping routed to: {next_node}")


class TestParallelGatewayExecution:
    """Test parallel gateway execution"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_parallel_gateway_fork(self, storage):
        """Test parallel gateway creates multiple tokens"""
        process_id = storage.deploy_process(
            name="Parallel Execution",
            description="Test fork behavior",
            bpmn_content="""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                              xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
                <bpmn:process id="parallelProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:parallelGateway id="gatewayFork"/>
                    <bpmn:serviceTask id="task1" name="Task A" camunda:topic="task_a"/>
                    <bpmn:serviceTask id="task2" name="Task B" camunda:topic="task_b"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gatewayFork"/>
                    <bpmn:sequenceFlow id="flow2" sourceRef="gatewayFork" targetRef="task1"/>
                    <bpmn:sequenceFlow id="flow3" sourceRef="gatewayFork" targetRef="task2"/>
                    <bpmn:sequenceFlow id="flow4" sourceRef="task1" targetRef="end1"/>
                    <bpmn:sequenceFlow id="flow5" sourceRef="task2" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>""",
        )

        # Register handlers to track execution
        executed_tasks = []

        def task_a_handler(instance_id, variables):
            executed_tasks.append("A")
            return variables

        def task_b_handler(instance_id, variables):
            executed_tasks.append("B")
            return variables

        storage.register_topic_handler("task_a", task_a_handler)
        storage.register_topic_handler("task_b", task_b_handler)

        result = storage.create_instance(process_id=process_id)
        instance_id = result["id"]

        instance = storage.get_instance(instance_id)
        print(f"Parallel execution - instance status: {instance['status']}")

        # Check that parallel gateway is recognized
        process_graph = storage.get_process_graph(process_id)
        gateway_type = process_graph.value(
            URIRef("http://example.org/bpmn/gatewayFork"),
            URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
        )
        assert "parallelGateway" in str(gateway_type)
        print("Parallel gateway recognized in process definition")

    def test_count_incoming_flows(self, storage):
        """Test counting incoming flows to a gateway"""
        process_id = storage.deploy_process(
            name="Parallel Process",
            description="Test incoming flow counting",
            bpmn_content="""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                <bpmn:process id="parallelCountProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:serviceTask id="task1"/>
                    <bpmn:serviceTask id="task2"/>
                    <bpmn:parallelGateway id="gatewayJoin"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flowStart" sourceRef="start1" targetRef="task1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="task1" targetRef="gatewayJoin"/>
                    <bpmn:sequenceFlow id="flow2" sourceRef="task2" targetRef="gatewayJoin"/>
                    <bpmn:sequenceFlow id="flow3" sourceRef="gatewayJoin" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>""",
        )

        gateway_uri = URIRef("http://example.org/bpmn/gatewayJoin")
        count = storage._count_incoming_flows(gateway_uri)
        assert count == 2, f"Should have 2 incoming flows, got {count}"
        print(f"Gateway has {count} incoming flows")


class TestParallelGatewayHelperMethods:
    """Test helper methods for parallel gateway operations"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_merge_parallel_tokens(self, storage):
        """Test merging multiple parallel tokens"""
        from rdflib import URIRef, RDF, Literal
        from src.api.storage import INST

        process_id = storage.deploy_process(
            name="Merge Test",
            description="Test token merging",
            bpmn_content="""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                <bpmn:process id="mergeProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:parallelGateway id="gatewayFork"/>
                    <bpmn:serviceTask id="task1"/>
                    <bpmn:serviceTask id="task2"/>
                    <bpmn:parallelGateway id="gatewayJoin"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gatewayFork"/>
                    <bpmn:sequenceFlow id="flow2" sourceRef="gatewayFork" targetRef="task1"/>
                    <bpmn:sequenceFlow id="flow3" sourceRef="gatewayFork" targetRef="task2"/>
                    <bpmn:sequenceFlow id="flow4" sourceRef="task1" targetRef="gatewayJoin"/>
                    <bpmn:sequenceFlow id="flow5" sourceRef="task2" targetRef="gatewayJoin"/>
                    <bpmn:sequenceFlow id="flow6" sourceRef="gatewayJoin" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>""",
        )

        result = storage.create_instance(process_id=process_id)
        instance_id = result["id"]
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        gateway_join_uri = URIRef("http://example.org/bpmn/gatewayJoin")
        end_event_uri = URIRef("http://example.org/bpmn/end1")

        token1_uri = URIRef(f"http://example.org/instance/token_{instance_id}_token1")
        token2_uri = URIRef(f"http://example.org/instance/token_{instance_id}_token2")

        storage.instances_graph.add((token1_uri, RDF.type, INST.Token))
        storage.instances_graph.add((token1_uri, INST.belongsTo, instance_uri))
        storage.instances_graph.add((token1_uri, INST.status, Literal("ACTIVE")))
        storage.instances_graph.add((token1_uri, INST.currentNode, gateway_join_uri))
        storage.instances_graph.add((instance_uri, INST.hasToken, token1_uri))

        storage.instances_graph.add((token2_uri, RDF.type, INST.Token))
        storage.instances_graph.add((token2_uri, INST.belongsTo, instance_uri))
        storage.instances_graph.add((token2_uri, INST.status, Literal("WAITING")))
        storage.instances_graph.add((token2_uri, INST.currentNode, gateway_join_uri))
        storage.instances_graph.add((instance_uri, INST.hasToken, token2_uri))

        initial_token_count = len(
            list(storage.instances_graph.objects(instance_uri, INST.hasToken))
        )
        print(f"Initial token count: {initial_token_count}")

        storage._merge_parallel_tokens(
            instance_uri, gateway_join_uri, instance_id, end_event_uri
        )

        token1_status = storage.instances_graph.value(token1_uri, INST.status)
        token2_status = storage.instances_graph.value(token2_uri, INST.status)

        assert str(token1_status) == "CONSUMED"
        assert str(token2_status) == "CONSUMED"
        print(f"Both tokens consumed after merge")

    def test_count_incoming_flows_helper(self, storage):
        """Test counting incoming flows to a gateway using helper method"""
        from rdflib import URIRef

        process_id = storage.deploy_process(
            name="Incoming Flows Test",
            description="Test incoming flow counting",
            bpmn_content="""<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
                <bpmn:process id="incomingProc">
                    <bpmn:startEvent id="start1"/>
                    <bpmn:serviceTask id="task1"/>
                    <bpmn:serviceTask id="task2"/>
                    <bpmn:parallelGateway id="gatewayJoin"/>
                    <bpmn:endEvent id="end1"/>
                    <bpmn:sequenceFlow id="flowStart" sourceRef="start1" targetRef="task1"/>
                    <bpmn:sequenceFlow id="flow1" sourceRef="task1" targetRef="gatewayJoin"/>
                    <bpmn:sequenceFlow id="flow2" sourceRef="task2" targetRef="gatewayJoin"/>
                    <bpmn:sequenceFlow id="flow3" sourceRef="gatewayJoin" targetRef="end1"/>
                </bpmn:process>
            </bpmn:definitions>""",
        )

        gateway_uri = URIRef("http://example.org/bpmn/gatewayJoin")
        count = storage._count_incoming_flows(gateway_uri)
        assert count == 2, f"Should have 2 incoming flows, got {count}"
        print(f"Gateway has {count} incoming flows")


def test_gateway_conversion_to_graph():
    """Test that gateway conditions are properly stored in RDF graph"""
    from src.conversion.bpmn2rdf import BPMNToRDFConverter
    import io

    bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                      xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
        <bpmn:process id="testProc">
            <bpmn:startEvent id="start1"/>
            <bpmn:exclusiveGateway id="gateway1"/>
            <bpmn:endEvent id="end1"/>
            <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="gateway1"/>
            <bpmn:sequenceFlow id="flow2" sourceRef="gateway1" targetRef="end1">
                <bpmn:conditionExpression xsi:type="tFormalExpression" camunda:expression="${active == true}"/>
            </bpmn:sequenceFlow>
        </bpmn:process>
    </bpmn:definitions>"""

    converter = BPMNToRDFConverter()
    graph = converter.parse_bpmn_to_graph(io.StringIO(bpmn))

    flow_uri = URIRef("http://example.org/bpmn/flow2")

    condition = graph.value(
        flow_uri, URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#conditionQuery")
    )
    assert condition is not None, "Condition query should be stored in graph"

    condition_str = str(condition)
    print(f"\nCondition query stored: {condition_str}")

    assert "ASK" in condition_str, "Condition should be SPARQL ASK query"
    assert "active" in condition_str, "Condition should reference variable"
