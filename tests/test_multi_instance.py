#!/usr/bin/env python3
"""
Multi-Instance Activities Tests
Tests parallel and sequential multi-instance task execution
"""

import pytest
from rdflib import Graph, Namespace, URIRef, Literal, RDF
import tempfile


class TestMultiInstanceActivities:
    """Test multi-instance activity execution"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService, INST

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def parallel_mi_bpmn(self):
        """BPMN with parallel multi-instance service task"""
        return """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://bpmn.io/schema/multi-instance">
            <bpmn:process id="parallelMIProcess" name="Parallel Multi-Instance Process" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="taskReview" name="Review Document"
                                  camunda:topic="review_document">
                    <bpmn:multiInstanceLoopCharacteristics isParallel="true">
                        <bpmn:loopCardinality>3</bpmn:loopCardinality>
                    </bpmn:multiInstanceLoopCharacteristics>
                </bpmn:serviceTask>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="taskReview"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="taskReview" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

    @pytest.fixture
    def sequential_mi_bpmn(self):
        """BPMN with sequential multi-instance service task"""
        return """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://bpmn.io/schema/multi-instance">
            <bpmn:process id="sequentialMIProcess" name="Sequential Multi-Instance Process" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="taskApprove" name="Approve Step"
                                  camunda:topic="approve_step">
                    <bpmn:multiInstanceLoopCharacteristics isSequential="true">
                        <bpmn:loopCardinality>2</bpmn:loopCardinality>
                    </bpmn:multiInstanceLoopCharacteristics>
                </bpmn:serviceTask>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="taskApprove"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="taskApprove" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

    def test_detect_multi_instance(self, storage, parallel_mi_bpmn):
        """Test detection of multi-instance characteristics"""
        process_id = storage.deploy_process(
            name="Parallel MI Process",
            description="Test parallel MI detection",
            bpmn_content=parallel_mi_bpmn,
        )

        task_uri = URIRef("http://example.org/bpmn/taskReview")
        mi_info = storage._is_multi_instance(task_uri)

        assert mi_info["is_multi_instance"] is True
        assert mi_info["is_parallel"] is True
        assert mi_info["is_sequential"] is False
        assert mi_info["loop_cardinality"] == "3"
        print(f"Multi-instance info: {mi_info}")

    def test_detect_sequential_multi_instance(self, storage, sequential_mi_bpmn):
        """Test detection of sequential multi-instance characteristics"""
        process_id = storage.deploy_process(
            name="Sequential MI Process",
            description="Test sequential MI detection",
            bpmn_content=sequential_mi_bpmn,
        )

        task_uri = URIRef("http://example.org/bpmn/taskApprove")
        mi_info = storage._is_multi_instance(task_uri)

        assert mi_info["is_multi_instance"] is True
        assert mi_info["is_parallel"] is False
        assert mi_info["is_sequential"] is True
        assert mi_info["loop_cardinality"] == "2"
        print(f"Multi-instance info: {mi_info}")

    def test_parallel_multi_instance_execution(self, storage, parallel_mi_bpmn):
        """Test parallel multi-instance creates multiple tokens"""
        from src.api.storage import INST

        process_id = storage.deploy_process(
            name="Parallel MI Process",
            description="Test parallel MI",
            bpmn_content=parallel_mi_bpmn,
        )

        execution_count = []

        def review_handler(instance_id, variables):
            execution_count.append(instance_id)
            return {"reviewed": True, "item": variables.get("item", "N/A")}

        storage.register_topic_handler("review_document", review_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"documentId": "DOC-001"},
        )

        instance_id = result["id"]
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        mi_tokens = []
        for token_uri in storage.instances_graph.objects(instance_uri, INST.hasToken):
            status = storage.instances_graph.value(token_uri, INST.status)
            current_node = storage.instances_graph.value(token_uri, INST.currentNode)
            if current_node and str(current_node).endswith("taskReview"):
                mi_tokens.append(token_uri)

        assert len(mi_tokens) >= 3, (
            f"Expected at least 3 tokens at MI node, got {len(mi_tokens)}"
        )
        assert len(execution_count) == 3, (
            f"Expected handler to execute 3 times, got {len(execution_count)}"
        )
        print("Parallel multi-instance created 3 tokens and executed handler 3 times")

    def test_sequential_multi_instance_execution(self, storage, sequential_mi_bpmn):
        """Test sequential multi-instance creates one token at a time"""
        from src.api.storage import INST

        process_id = storage.deploy_process(
            name="Sequential MI Process",
            description="Test sequential MI execution",
            bpmn_content=sequential_mi_bpmn,
        )

        execution_count = []

        def approve_handler(instance_id, variables):
            execution_count.append(len(execution_count) + 1)
            return {"approved": True, "step": len(execution_count)}

        storage.register_topic_handler("approve_step", approve_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"requestId": "REQ-001"},
        )

        instance_id = result["id"]
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        assert len(execution_count) == 2, (
            f"Expected handler to execute 2 times for sequential MI, got {len(execution_count)}"
        )
        print("Sequential multi-instance executed handler 2 times")

    def test_multi_instance_regular_task(self, storage):
        """Test that regular (non-MI) tasks work correctly"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
            <bpmn:process id="regularProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Regular Task" camunda:topic="regular_task"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Regular Process",
            description="Test regular task detection",
            bpmn_content=bpmn,
        )

        task_uri = URIRef("http://example.org/bpmn/task1")
        mi_info = storage._is_multi_instance(task_uri)

        assert mi_info["is_multi_instance"] is False
        assert mi_info["is_parallel"] is False
        assert mi_info["is_sequential"] is False
        print("Regular task correctly identified as non-MI")

    def test_parallel_mi_advance_after_completion(self, storage, parallel_mi_bpmn):
        """Test that parallel MI advances after all instances complete"""
        from src.api.storage import INST

        process_id = storage.deploy_process(
            name="Parallel MI Process",
            description="Test parallel MI completion",
            bpmn_content=parallel_mi_bpmn,
        )

        execution_count = []

        def review_handler(instance_id, variables):
            execution_count.append(len(execution_count) + 1)
            return {"reviewed": True}

        storage.register_topic_handler("review_document", review_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"documentId": "DOC-002"},
        )

        instance_id = result["id"]
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        assert len(execution_count) == 3, (
            f"Expected handler to execute 3 times, got {len(execution_count)}"
        )

        instance = storage.get_instance(instance_id)
        print(f"Instance status: {instance['status']}")

        mi_tokens = []
        for token_uri in storage.instances_graph.objects(instance_uri, INST.hasToken):
            loop_instance = storage.instances_graph.value(token_uri, INST.loopInstance)
            if loop_instance is not None:
                mi_tokens.append(token_uri)

        assert len(mi_tokens) == 3, f"Expected 3 MI tokens, got {len(mi_tokens)}"
        print(f"Parallel MI completed, {len(execution_count)} instances processed")


class TestMultiInstanceUserTask:
    """Test multi-instance user task execution"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService, INST

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def user_task_mi_bpmn(self):
        """BPMN with parallel multi-instance user task"""
        return """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://bpmn.io/schema/multi-instance">
            <bpmn:process id="userTaskMIProcess" name="User Task MI Process" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:userTask id="taskVote" name="Cast Vote" camunda:assignee="teamMember">
                    <bpmn:multiInstanceLoopCharacteristics isParallel="true">
                        <bpmn:loopCardinality>5</bpmn:loopCardinality>
                    </bpmn:multiInstanceLoopCharacteristics>
                </bpmn:userTask>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="taskVote"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="taskVote" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

    def test_user_task_multi_instance(self, storage, user_task_mi_bpmn):
        """Test multi-instance user task creates multiple task instances"""
        from src.api.storage import INST

        process_id = storage.deploy_process(
            name="User Task MI Process",
            description="Test user task MI",
            bpmn_content=user_task_mi_bpmn,
        )

        result = storage.create_instance(
            process_id=process_id,
            variables={"voteTopic": "Budget 2024"},
        )

        instance_id = result["id"]
        instance_uri = URIRef(f"http://example.org/instance/{instance_id}")

        waiting_tokens = []
        for token_uri in storage.instances_graph.objects(instance_uri, INST.hasToken):
            status = storage.instances_graph.value(token_uri, INST.status)
            if status and str(status) == "WAITING":
                waiting_tokens.append(token_uri)

        assert len(waiting_tokens) == 5, (
            f"Expected 5 waiting tokens, got {len(waiting_tokens)}"
        )
        print(f"User task MI created {len(waiting_tokens)} waiting tokens")


class TestMultiInstanceLoopCardinality:
    """Test different loop cardinality scenarios"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService, INST

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_dynamic_cardinality(self, storage):
        """Test that cardinality is parsed correctly"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
            <bpmn:process id="dynamicMIProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Dynamic Task" camunda:topic="dynamic_task">
                    <bpmn:multiInstanceLoopCharacteristics isParallel="true">
                        <bpmn:loopCardinality>${numberOfItems}</bpmn:loopCardinality>
                    </bpmn:multiInstanceLoopCharacteristics>
                </bpmn:serviceTask>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Dynamic MI Process",
            description="Test dynamic cardinality",
            bpmn_content=bpmn,
        )

        task_uri = URIRef("http://example.org/bpmn/task1")
        mi_info = storage._is_multi_instance(task_uri)

        assert mi_info["is_multi_instance"] is True
        assert mi_info["loop_cardinality"] == "${numberOfItems}"
        print(f"Dynamic cardinality parsed: {mi_info['loop_cardinality']}")

    def test_single_instance(self, storage):
        """Test that single cardinality creates one instance"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn">
            <bpmn:process id="singleMIProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Single Task" camunda:topic="single_task">
                    <bpmn:multiInstanceLoopCharacteristics isParallel="true">
                        <bpmn:loopCardinality>1</bpmn:loopCardinality>
                    </bpmn:multiInstanceLoopCharacteristics>
                </bpmn:serviceTask>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Single MI Process",
            description="Test single cardinality",
            bpmn_content=bpmn,
        )

        task_uri = URIRef("http://example.org/bpmn/task1")
        mi_info = storage._is_multi_instance(task_uri)

        assert mi_info["is_multi_instance"] is True
        assert mi_info["loop_cardinality"] == "1"
        print("Single instance cardinality detected")


class TestMessageEndEvents:
    """Tests for message end events"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService, INST

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_message_end_event(self, storage):
        """Test that message end event throws a message and completes"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/message">
            <bpmn:process id="MessageEndProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Task 1" camunda:topic="task1"/>
                <bpmn:endEvent id="messageEnd" name="Send Notification">
                    <bpmn:messageEventDefinition camunda:message="order_confirmed"/>
                </bpmn:endEvent>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="messageEnd"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Message End Event Test",
            description="Test message end event",
            bpmn_content=bpmn,
        )

        task_executed = []

        def task_handler(instance_id, variables, loop_idx=None):
            task_executed.append(variables.get("orderId"))
            return {"done": True}

        storage.register_topic_handler("task1", task_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"orderId": "ORD-001"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        assert len(task_executed) == 1
        assert task_executed[0] == "ORD-001"

        events = storage.get_instance_audit_log(instance_id)
        message_thrown_events = [e for e in events if e["type"] == "MESSAGE_THROWN"]
        assert len(message_thrown_events) == 1
        assert "order_confirmed" in message_thrown_events[0]["details"]

        print(f"Message end event test passed: {message_thrown_events}")

    def test_message_end_event_in_subprocess(self, storage):
        """Test message end event inside an expanded subprocess"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/message">
            <bpmn:process id="SubprocessMessageEnd" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:subProcess id="subProcess" name="Processing Subprocess">
                    <bpmn:startEvent id="subStart"/>
                    <bpmn:serviceTask id="processTask" name="Process"
                                      camunda:topic="process"/>
                    <bpmn:endEvent id="subEnd" name="Complete">
                        <bpmn:messageEventDefinition camunda:message="processing_complete"/>
                    </bpmn:endEvent>
                    <bpmn:sequenceFlow id="subFlow1" sourceRef="subStart" targetRef="processTask"/>
                    <bpmn:sequenceFlow id="subFlow2" sourceRef="processTask" targetRef="subEnd"/>
                </bpmn:subProcess>
                <bpmn:endEvent id="mainEnd" name="Main End"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="subProcess"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="subProcess" targetRef="mainEnd"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Subprocess Message End Test",
            description="Test message end event in subprocess",
            bpmn_content=bpmn,
        )

        process_called = []

        def process_handler(instance_id, variables, loop_idx=None):
            process_called.append(variables.get("orderId"))
            return {"processed": True}

        storage.register_topic_handler("process", process_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"orderId": "ORD-002"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        assert len(process_called) == 1
        assert process_called[0] == "ORD-002"

        events = storage.get_instance_audit_log(instance_id)
        message_events = [e for e in events if "MESSAGE" in e["type"]]
        assert len(message_events) >= 1

        message_event = [
            e
            for e in events
            if e["type"] == "MESSAGE_THROWN"
            and "processing_complete" in e.get("details", "")
        ]
        assert len(message_event) == 1

        print(f"Subprocess message end event test passed")

    def test_multiple_message_end_events(self, storage):
        """Test process with multiple message end events (different paths)"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/message">
            <bpmn:process id="MultipleMessageEnd" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="decisionTask" name="Make Decision"
                                  camunda:topic="decision"/>
                <bpmn:exclusiveGateway id="gateway" name="Decision Point"/>
                <bpmn:serviceTask id="approvedTask" name="Process Approval"
                                  camunda:topic="approved"/>
                <bpmn:serviceTask id="rejectedTask" name="Process Rejection"
                                  camunda:topic="rejected"/>
                <bpmn:endEvent id="approvedEnd" name="Approved">
                    <bpmn:messageEventDefinition camunda:message="order_approved"/>
                </bpmn:endEvent>
                <bpmn:endEvent id="rejectedEnd" name="Rejected">
                    <bpmn:messageEventDefinition camunda:message="order_rejected"/>
                </bpmn:endEvent>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="decisionTask"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="decisionTask" targetRef="gateway"/>
                <bpmn:sequenceFlow id="flow3" sourceRef="gateway" targetRef="approvedTask"/>
                <bpmn:sequenceFlow id="flow4" sourceRef="approvedTask" targetRef="approvedEnd"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Multiple Message End Events Test",
            description="Test multiple message end events",
            bpmn_content=bpmn,
        )

        def approved_handler(instance_id, variables, loop_idx=None):
            return {"done": True}

        def rejected_handler(instance_id, variables, loop_idx=None):
            return {"done": True}

        def decision_handler(instance_id, variables, loop_idx=None):
            storage.set_instance_variable(instance_id, "decision", "approved")
            return {"decision": "approved"}

        storage.register_topic_handler("approved", approved_handler)
        storage.register_topic_handler("rejected", rejected_handler)
        storage.register_topic_handler("decision", decision_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"orderId": "ORD-003"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        events = storage.get_instance_audit_log(instance_id)
        message_events = [e for e in events if e["type"] == "MESSAGE_THROWN"]
        assert len(message_events) == 1
        assert "order_approved" in message_events[0]["details"]

        print(f"Multiple message end events test passed")

    def test_regular_end_event(self, storage):
        """Test that regular end events still work correctly"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/message">
            <bpmn:process id="RegularEndProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Task 1" camunda:topic="task1"/>
                <bpmn:endEvent id="regularEnd" name="Complete"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="regularEnd"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Regular End Event Test",
            description="Test regular end event",
            bpmn_content=bpmn,
        )

        def task_handler(instance_id, variables, loop_idx=None):
            return {"done": True}

        storage.register_topic_handler("task1", task_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"orderId": "ORD-004"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        events = storage.get_instance_audit_log(instance_id)
        end_events = [e for e in events if e["type"] == "END"]
        assert len(end_events) == 1
        message_events = [e for e in events if "MESSAGE" in e["type"]]
        assert len(message_events) == 0

        print(f"Regular end event test passed")


class TestInclusiveGateway:
    """Tests for inclusive gateway support"""

    @pytest.fixture
    def storage(self):
        from src.api.storage import RDFStorageService, INST

        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_inclusive_gateway_multiple_paths(self, storage):
        """Test inclusive gateway forks to multiple paths based on conditions"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/inclusive">
            <bpmn:process id="InclusiveProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Task 1" camunda:topic="task1"/>
                <bpmn:inclusiveGateway id="gateway1"/>
                <bpmn:serviceTask id="taskA" name="Task A" camunda:topic="taskA"/>
                <bpmn:serviceTask id="taskB" name="Task B" camunda:topic="taskB"/>
                <bpmn:serviceTask id="taskC" name="Task C" camunda:topic="taskC"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flowA" sourceRef="gateway1" targetRef="taskA">
                    <conditionExpression camunda:expression="${approved == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowB" sourceRef="gateway1" targetRef="taskB">
                    <conditionExpression camunda:expression="${needsReview == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowC" sourceRef="gateway1" targetRef="taskC">
                    <conditionExpression camunda:expression="${urgent == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowEnd" sourceRef="taskA" targetRef="end1"/>
                <bpmn:sequenceFlow id="flowEndB" sourceRef="taskB" targetRef="end1"/>
                <bpmn:sequenceFlow id="flowEndC" sourceRef="taskC" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Inclusive Gateway Multiple Paths",
            description="Test inclusive gateway with multiple paths",
            bpmn_content=bpmn,
        )

        task_calls = []

        def task_handler(instance_id, variables, loop_idx=None):
            task_calls.append("called")
            return {"done": True}

        storage.register_topic_handler("task1", task_handler)
        storage.register_topic_handler("taskA", task_handler)
        storage.register_topic_handler("taskB", task_handler)
        storage.register_topic_handler("taskC", task_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "orderId": "ORD-001",
                "approved": "true",
                "needsReview": "true",
                "urgent": "true",
            },
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        assert len(task_calls) == 4

        events = storage.get_instance_audit_log(instance_id)
        fork_events = [e for e in events if "INCLUSIVE_GATEWAY_FORK" in e["type"]]
        assert len(fork_events) == 1
        assert "3 paths" in fork_events[0]["details"]

        print(f"Inclusive gateway multiple paths test passed: {len(task_calls)} tasks")

    def test_inclusive_gateway_single_path(self, storage):
        """Test inclusive gateway with only one condition true"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/inclusive">
            <bpmn:process id="InclusiveProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Task 1" camunda:topic="task1"/>
                <bpmn:inclusiveGateway id="gateway1"/>
                <bpmn:serviceTask id="taskA" name="Task A" camunda:topic="taskA"/>
                <bpmn:serviceTask id="taskB" name="Task B" camunda:topic="taskB"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flowA" sourceRef="gateway1" targetRef="taskA">
                    <conditionExpression camunda:expression="${approved == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowB" sourceRef="gateway1" targetRef="taskB">
                    <conditionExpression camunda:expression="${needsReview == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowEndA" sourceRef="taskA" targetRef="end1"/>
                <bpmn:sequenceFlow id="flowEndB" sourceRef="taskB" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Inclusive Gateway Single Path",
            description="Test inclusive gateway with single path",
            bpmn_content=bpmn,
        )

        task_calls = []

        def task_handler(instance_id, variables, loop_idx=None):
            task_calls.append("called")
            return {"done": True}

        storage.register_topic_handler("task1", task_handler)
        storage.register_topic_handler("taskA", task_handler)
        storage.register_topic_handler("taskB", task_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={
                "orderId": "ORD-002",
                "approved": "true",
                "needsReview": "false",
            },
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        assert len(task_calls) == 2

        print(f"Inclusive gateway single path test passed: {len(task_calls)} tasks")

    def test_inclusive_gateway_no_conditions(self, storage):
        """Test inclusive gateway with no conditions (all paths taken)"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/inclusive">
            <bpmn:process id="InclusiveProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Task 1" camunda:topic="task1"/>
                <bpmn:inclusiveGateway id="gateway1"/>
                <bpmn:serviceTask id="taskA" name="Task A" camunda:topic="taskA"/>
                <bpmn:serviceTask id="taskB" name="Task B" camunda:topic="taskB"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flowA" sourceRef="gateway1" targetRef="taskA"/>
                <bpmn:sequenceFlow id="flowB" sourceRef="gateway1" targetRef="taskB"/>
                <bpmn:sequenceFlow id="flowEndA" sourceRef="taskA" targetRef="end1"/>
                <bpmn:sequenceFlow id="flowEndB" sourceRef="taskB" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Inclusive Gateway No Conditions",
            description="Test inclusive gateway with no conditions",
            bpmn_content=bpmn,
        )

        task_calls = []

        def task_handler(instance_id, variables, loop_idx=None):
            task_calls.append("called")
            return {"done": True}

        storage.register_topic_handler("task1", task_handler)
        storage.register_topic_handler("taskA", task_handler)
        storage.register_topic_handler("taskB", task_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"orderId": "ORD-003"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        assert len(task_calls) == 3

        print(f"Inclusive gateway no conditions test passed: {len(task_calls)} tasks")

    def test_inclusive_gateway_parallel_join(self, storage):
        """Test inclusive gateway join behavior (wait for all paths)"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://test.org/inclusive">
            <bpmn:process id="InclusiveProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" name="Task 1" camunda:topic="task1"/>
                <bpmn:inclusiveGateway id="gateway1"/>
                <bpmn:serviceTask id="taskA" name="Task A" camunda:topic="taskA"/>
                <bpmn:serviceTask id="taskB" name="Task B" camunda:topic="taskB"/>
                <bpmn:inclusiveGateway id="gateway2"/>
                <bpmn:serviceTask id="taskFinal" name="Final Task" camunda:topic="taskFinal"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="gateway1"/>
                <bpmn:sequenceFlow id="flowA" sourceRef="gateway1" targetRef="taskA">
                    <conditionExpression camunda:expression="${pathA == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowB" sourceRef="gateway1" targetRef="taskB">
                    <conditionExpression camunda:expression="${pathB == true}"/>
                </bpmn:sequenceFlow>
                <bpmn:sequenceFlow id="flowToJoin" sourceRef="taskA" targetRef="gateway2"/>
                <bpmn:sequenceFlow id="flowToJoinB" sourceRef="taskB" targetRef="gateway2"/>
                <bpmn:sequenceFlow id="flowFinal" sourceRef="gateway2" targetRef="taskFinal"/>
                <bpmn:sequenceFlow id="flowEnd" sourceRef="taskFinal" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Inclusive Gateway Join",
            description="Test inclusive gateway join behavior",
            bpmn_content=bpmn,
        )

        task_calls = []

        def task_handler(instance_id, variables, loop_idx=None):
            task_calls.append("called")
            return {"done": True}

        storage.register_topic_handler("task1", task_handler)
        storage.register_topic_handler("taskA", task_handler)
        storage.register_topic_handler("taskB", task_handler)
        storage.register_topic_handler("taskFinal", task_handler)

        result = storage.create_instance(
            process_id=process_id,
            variables={"orderId": "ORD-004", "pathA": "true", "pathB": "true"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)
        assert instance["status"] == "COMPLETED"

        assert len(task_calls) == 4

        print(f"Inclusive gateway join test passed: {len(task_calls)} tasks")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
