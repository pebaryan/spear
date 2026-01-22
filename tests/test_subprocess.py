"""
Tests for subprocess functionality in SPEAR BPMN engine.

Tests cover:
- Expanded (embedded) subprocesses
- Call activities (collapsed subprocesses)
- Event subprocesses
"""

import tempfile
import pytest
from rdflib import URIRef, Namespace, RDF

from src.api.storage import RDFStorageService, INST


class TestExpandedSubprocess:
    """Tests for expanded (embedded) subprocesses"""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp directory"""
        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage

    def test_parse_expanded_subprocess(self, storage):
        """Test parsing of expanded subprocess elements"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://example.org/">
            <bpmn:process id="testProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:subProcess id="subProcess1" name="Embedded Subprocess">
                    <bpmn:startEvent id="subStart"/>
                    <bpmn:serviceTask id="subTask" camunda:topic="sub_task"/>
                    <bpmn:endEvent id="subEnd"/>
                    <bpmn:sequenceFlow id="subFlow1" sourceRef="subStart" targetRef="subTask"/>
                    <bpmn:sequenceFlow id="subFlow2" sourceRef="subTask" targetRef="subEnd"/>
                </bpmn:subProcess>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="subProcess1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="subProcess1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Expanded Subprocess Test",
            description="Test expanded subprocess parsing",
            bpmn_content=bpmn,
        )

        # Check subprocess type
        subprocess_uri = URIRef("http://example.org/bpmn/subProcess1")
        is_subprocess = False
        for s, p, o in storage.definitions_graph.triples((subprocess_uri, None, None)):
            if "ExpandedSubprocess" in str(o):
                is_subprocess = True
                break

        assert is_subprocess, "Subprocess should be marked as ExpandedSubprocess"

    def test_execute_expanded_subprocess(self, storage):
        """Test execution of expanded subprocess"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://example.org/">
            <bpmn:process id="testProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:subProcess id="subProcess1" name="Embedded Subprocess">
                    <bpmn:startEvent id="subStart"/>
                    <bpmn:serviceTask id="subTask" camunda:topic="sub_task"/>
                    <bpmn:endEvent id="subEnd"/>
                    <bpmn:sequenceFlow id="subFlow1" sourceRef="subStart" targetRef="subTask"/>
                    <bpmn:sequenceFlow id="subFlow2" sourceRef="subTask" targetRef="subEnd"/>
                </bpmn:subProcess>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="subProcess1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="subProcess1" targetRef="end1"/>
            </bpmn:process>
        </bpmn:definitions>"""

        call_log = []

        def sub_task_handler(instance_id, variables):
            call_log.append(("sub_task", instance_id))
            return {"completed": True}

        storage.register_topic_handler("sub_task", sub_task_handler)

        process_id = storage.deploy_process(
            name="Expanded Subprocess Test",
            description="Test expanded subprocess execution",
            bpmn_content=bpmn,
        )

        result = storage.create_instance(
            process_id=process_id,
            variables={"documentId": "DOC-001"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)

        assert instance["status"] == "COMPLETED", "Instance should complete"
        assert len(call_log) == 1, "Subprocess task should be executed"
        assert call_log[0][0] == "sub_task", "Should execute sub_task handler"


class TestCallActivity:
    """Tests for call activities (collapsed subprocesses)"""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp directory"""
        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage

    def test_parse_call_activity(self, storage):
        """Test parsing of call activity elements"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://example.org/">
            <bpmn:process id="testProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:callActivity id="callActivity1" name="Call Subprocess"
                                   calledElement="subProcessDef"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="callActivity1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="callActivity1" targetRef="end1"/>
            </bpmn:process>
            <bpmn:process id="subProcessDef" isExecutable="false">
                <bpmn:startEvent id="subStart"/>
                <bpmn:serviceTask id="subTask" camunda:topic="sub_task"/>
                <bpmn:endEvent id="subEnd"/>
                <bpmn:sequenceFlow id="subFlow1" sourceRef="subStart" targetRef="subTask"/>
                <bpmn:sequenceFlow id="subFlow2" sourceRef="subTask" targetRef="subEnd"/>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Call Activity Test",
            description="Test call activity parsing",
            bpmn_content=bpmn,
        )

        # Check call activity type
        call_activity_uri = URIRef("http://example.org/bpmn/callActivity1")
        is_call_activity = False
        for s, p, o in storage.definitions_graph.triples(
            (call_activity_uri, RDF.type, None)
        ):
            if "callactivity" in str(o).lower():
                is_call_activity = True
                break

        assert is_call_activity, "Call activity should be marked as CallActivity"

        # Check calledElement reference
        called_element = storage.definitions_graph.value(
            call_activity_uri,
            URIRef("http://dkm.fbk.eu/index.php/BPMN2_Ontology#calledElement"),
        )
        assert called_element is not None, "Call activity should have calledElement"


class TestEventSubprocess:
    """Tests for event subprocesses"""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp directory"""
        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage

    def test_parse_event_subprocess(self, storage):
        """Test parsing of event subprocess elements"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://example.org/">
            <bpmn:process id="testProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:serviceTask id="task1" camunda:topic="task1"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
                <bpmn:subProcess id="eventSubProcess" name="Event Subprocess"
                                 triggeredByEvent="true">
                    <bpmn:startEvent id="eventStart">
                        <bpmn:messageEventDefinition/>
                    </bpmn:startEvent>
                    <bpmn:serviceTask id="eventTask" camunda:topic="event_task"/>
                    <bpmn:endEvent id="eventEnd"/>
                    <bpmn:sequenceFlow id="eventFlow1" sourceRef="eventStart" targetRef="eventTask"/>
                    <bpmn:sequenceFlow id="eventFlow2" sourceRef="eventTask" targetRef="eventEnd"/>
                </bpmn:subProcess>
            </bpmn:process>
        </bpmn:definitions>"""

        process_id = storage.deploy_process(
            name="Event Subprocess Test",
            description="Test event subprocess parsing",
            bpmn_content=bpmn,
        )

        # Check event subprocess type
        subprocess_uri = URIRef("http://example.org/bpmn/eventSubProcess")
        is_event_subprocess = False
        for s, p, o in storage.definitions_graph.triples((subprocess_uri, None, None)):
            if "EventSubprocess" in str(o):
                is_event_subprocess = True
                break

        assert is_event_subprocess, (
            "Event subprocess should be marked as EventSubprocess"
        )


class TestSubprocessCombinations:
    """Tests for combinations of subprocess types"""

    @pytest.fixture
    def storage(self):
        """Create a storage instance with temp directory"""
        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage

    def test_multiple_subprocess_types(self, storage):
        """Test process with multiple types of subprocesses"""
        bpmn = """<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                          xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
                          targetNamespace="http://example.org/">
            <bpmn:process id="testProcess" isExecutable="true">
                <bpmn:startEvent id="start1"/>
                <bpmn:subProcess id="expandedSub" name="Expanded Subprocess">
                    <bpmn:startEvent id="expStart"/>
                    <bpmn:serviceTask id="expTask" camunda:topic="exp_task"/>
                    <bpmn:endEvent id="expEnd"/>
                    <bpmn:sequenceFlow id="expFlow1" sourceRef="expStart" targetRef="expTask"/>
                    <bpmn:sequenceFlow id="expFlow2" sourceRef="expTask" targetRef="expEnd"/>
                </bpmn:subProcess>
                <bpmn:callActivity id="callAct" name="Call Activity"
                                   calledElement="reusableProcess"/>
                <bpmn:endEvent id="end1"/>
                <bpmn:sequenceFlow id="flow1" sourceRef="start1" targetRef="expandedSub"/>
                <bpmn:sequenceFlow id="flow2" sourceRef="expandedSub" targetRef="callAct"/>
                <bpmn:sequenceFlow id="flow3" sourceRef="callAct" targetRef="end1"/>
            </bpmn:process>
            <bpmn:process id="reusableProcess" isExecutable="false">
                <bpmn:startEvent id="reusStart"/>
                <bpmn:serviceTask id="reusTask" camunda:topic="reus_task"/>
                <bpmn:endEvent id="reusEnd"/>
                <bpmn:sequenceFlow id="reusFlow1" sourceRef="reusStart" targetRef="reusTask"/>
                <bpmn:sequenceFlow id="reusFlow2" sourceRef="reusTask" targetRef="reusEnd"/>
            </bpmn:process>
        </bpmn:definitions>"""

        call_log = []

        def exp_task_handler(instance_id, variables):
            call_log.append(("exp_task", instance_id))
            return {"completed": True}

        def reus_task_handler(instance_id, variables):
            call_log.append(("reus_task", instance_id))
            return {"completed": True}

        storage.register_topic_handler("exp_task", exp_task_handler)
        storage.register_topic_handler("reus_task", reus_task_handler)

        process_id = storage.deploy_process(
            name="Multiple Subprocess Types Test",
            description="Test multiple subprocess types",
            bpmn_content=bpmn,
        )

        result = storage.create_instance(
            process_id=process_id,
            variables={"documentId": "DOC-001"},
        )

        instance_id = result["id"]
        instance = storage.get_instance(instance_id)

        assert instance["status"] == "COMPLETED", "Instance should complete"
        assert len(call_log) == 2, "Should execute both subprocess tasks"
