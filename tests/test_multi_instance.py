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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
