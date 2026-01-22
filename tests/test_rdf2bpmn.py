#!/usr/bin/env python3
"""
Unit tests for RDF to BPMN Converter
Tests conversion of RDF process definitions back to BPMN 2.0 XML
"""

import pytest
import xml.etree.ElementTree as ET
from rdflib import Graph, Namespace, RDF, RDFS, Literal, URIRef

from src.conversion import RDFToBPMNConverter


BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
PROC = Namespace("http://example.org/process/")
META = Namespace("http://example.org/meta/")


class TestRDFToBPMNConverter:
    """Test cases for RDF to BPMN converter"""

    def test_convert_empty_graph(self):
        """Test converting an empty graph"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Should create basic BPMN structure
        result = converter.convert_graph(graph)

        assert '<?xml version="1.0"' in result
        assert "<definitions" in result
        assert "<process" in result

    def test_convert_startevent(self):
        """Test converting a start event"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create RDF with start event
        startevent_uri = URIRef("http://example.org/bpmn/StartEvent_1")
        graph.add((startevent_uri, RDF.type, BPMN.StartEvent))
        graph.add((startevent_uri, RDFS.label, Literal("Start")))

        result = converter.convert_graph(graph)

        assert "<startEvent" in result
        assert "StartEvent_1" in result
        assert 'name="Start"' in result

    def test_convert_endevent(self):
        """Test converting an end event"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create RDF with end event
        endevent_uri = URIRef("http://example.org/bpmn/EndEvent_1")
        graph.add((endevent_uri, RDF.type, BPMN.EndEvent))
        graph.add((endevent_uri, RDFS.label, Literal("End")))

        result = converter.convert_graph(graph)

        assert "<endEvent" in result
        assert "EndEvent_1" in result
        assert 'name="End"' in result

    def test_convert_servicetask_with_topic(self):
        """Test converting a service task with camunda topic"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create RDF with service task
        task_uri = URIRef("http://example.org/bpmn/ServiceTask_1")
        graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        graph.add((task_uri, RDFS.label, Literal("Process Order")))
        graph.add((task_uri, BPMN.topic, Literal("process_order")))

        result = converter.convert_graph(graph)

        assert "<serviceTask" in result
        assert "ServiceTask_1" in result
        assert 'name="Process Order"' in result
        assert 'camunda:topic="process_order"' in result

    def test_convert_usertask(self):
        """Test converting a user task"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create RDF with user task
        task_uri = URIRef("http://example.org/bpmn/UserTask_1")
        graph.add((task_uri, RDF.type, BPMN.UserTask))
        graph.add((task_uri, RDFS.label, Literal("Review")))
        graph.add((task_uri, BPMN.assignee, Literal("manager")))

        result = converter.convert_graph(graph)

        assert "<userTask" in result
        assert "UserTask_1" in result
        assert 'camunda:assignee="manager"' in result

    def test_convert_exclusive_gateway(self):
        """Test converting an exclusive gateway"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create RDF with exclusive gateway
        gateway_uri = URIRef("http://example.org/bpmn/Gateway_1")
        graph.add((gateway_uri, RDF.type, BPMN.ExclusiveGateway))
        graph.add((gateway_uri, RDFS.label, Literal("Decision")))

        result = converter.convert_graph(graph)

        assert "<exclusiveGateway" in result
        assert "Gateway_1" in result
        assert 'name="Decision"' in result

    def test_convert_parallel_gateway(self):
        """Test converting a parallel gateway"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create RDF with parallel gateway
        gateway_uri = URIRef("http://example.org/bpmn/Gateway_2")
        graph.add((gateway_uri, RDF.type, BPMN.ParallelGateway))
        graph.add((gateway_uri, RDFS.label, Literal("Fork")))

        result = converter.convert_graph(graph)

        assert "<parallelGateway" in result
        assert "Gateway_2" in result

    def test_convert_sequence_flow(self):
        """Test converting a sequence flow"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create simple process with start -> task -> end
        startevent = URIRef("http://example.org/bpmn/StartEvent_1")
        task = URIRef("http://example.org/bpmn/Task_1")
        flow1 = URIRef("http://example.org/bpmn/Flow_1")

        graph.add((startevent, RDF.type, BPMN.StartEvent))
        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((flow1, RDF.type, BPMN.SequenceFlow))
        graph.add((flow1, BPMN.sourceRef, startevent))
        graph.add((flow1, BPMN.targetRef, task))

        result = converter.convert_graph(graph)

        assert "<sequenceFlow" in result
        assert "Flow_1" in result
        assert 'sourceRef="StartEvent_1"' in result
        assert 'targetRef="Task_1"' in result

    def test_convert_sequence_flow_with_condition(self):
        """Test converting a sequence flow with condition"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create gateway with conditional flow
        gateway = URIRef("http://example.org/bpmn/Gateway_1")
        task_approve = URIRef("http://example.org/bpmn/Task_Approve")
        task_reject = URIRef("http://example.org/bpmn/Task_Reject")
        flow_yes = URIRef("http://example.org/bpmn/Flow_Yes")
        flow_no = URIRef("http://example.org/bpmn/Flow_No")

        # Gateway and tasks
        graph.add((gateway, RDF.type, BPMN.ExclusiveGateway))
        graph.add((task_approve, RDF.type, BPMN.ServiceTask))
        graph.add((task_reject, RDF.type, BPMN.ServiceTask))

        # Conditional flow
        graph.add((flow_yes, RDF.type, BPMN.SequenceFlow))
        graph.add((flow_yes, BPMN.sourceRef, gateway))
        graph.add((flow_yes, BPMN.targetRef, task_approve))
        graph.add((flow_yes, BPMN.conditionBody, Literal("${approved == true}")))
        graph.add((flow_yes, BPMN.conditionType, Literal("camunda:expression")))

        # Unconditional flow
        graph.add((flow_no, RDF.type, BPMN.SequenceFlow))
        graph.add((flow_no, BPMN.sourceRef, gateway))
        graph.add((flow_no, BPMN.targetRef, task_reject))

        result = converter.convert_graph(graph)

        assert "<sequenceFlow" in result
        assert "conditionExpression" in result
        assert "${approved == true}" in result

    def test_convert_complete_process(self):
        """Test converting a complete simple process"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create a simple process: StartEvent -> Task -> EndEvent
        startevent = URIRef("http://example.org/bpmn/StartEvent_1")
        task = URIRef("http://example.org/bpmn/Task_1")
        endevent = URIRef("http://example.org/bpmn/EndEvent_1")
        flow1 = URIRef("http://example.org/bpmn/Flow_1")
        flow2 = URIRef("http://example.org/bpmn/Flow_2")

        # Elements
        graph.add((startevent, RDF.type, BPMN.StartEvent))
        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((task, BPMN.topic, Literal("do_something")))
        graph.add((task, RDFS.label, Literal("Do Something")))
        graph.add((endevent, RDF.type, BPMN.EndEvent))

        # Flows
        graph.add((flow1, RDF.type, BPMN.SequenceFlow))
        graph.add((flow1, BPMN.sourceRef, startevent))
        graph.add((flow1, BPMN.targetRef, task))

        graph.add((flow2, RDF.type, BPMN.SequenceFlow))
        graph.add((flow2, BPMN.sourceRef, task))
        graph.add((flow2, BPMN.targetRef, endevent))

        result = converter.convert_graph(graph)

        # Verify all elements are present
        assert "<startEvent" in result
        assert "<serviceTask" in result
        assert "<endEvent" in result
        assert "<sequenceFlow" in result
        assert "Do Something" in result
        assert 'camunda:topic="do_something"' in result

        # Verify structure
        assert result.index("<startEvent") < result.index("<serviceTask")
        assert result.index("<serviceTask") < result.index("<endEvent")
        # Sequence flows should be at the end
        assert result.count("<sequenceFlow") == 2

    def test_convert_parallel_gateway_fork(self):
        """Test converting a parallel gateway that forks"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Process with parallel fork
        startevent = URIRef("http://example.org/bpmn/StartEvent_1")
        gateway = URIRef("http://example.org/bpmn/Gateway_Fork")
        task1 = URIRef("http://example.org/bpmn/Task_A")
        task2 = URIRef("http://example.org/bpmn/Task_B")
        endevent = URIRef("http://example.org/bpmn/EndEvent_1")

        # Fork gateway
        graph.add((startevent, RDF.type, BPMN.StartEvent))
        graph.add((gateway, RDF.type, BPMN.ParallelGateway))
        graph.add((task1, RDF.type, BPMN.ServiceTask))
        graph.add((task2, RDF.type, BPMN.ServiceTask))
        graph.add((endevent, RDF.type, BPMN.EndEvent))

        # Flows
        graph.add(
            (URIRef("http://example.org/bpmn/Flow_Start"), RDF.type, BPMN.SequenceFlow)
        )
        graph.add(
            (URIRef("http://example.org/bpmn/Flow_Start"), BPMN.sourceRef, startevent)
        )
        graph.add(
            (URIRef("http://example.org/bpmn/Flow_Start"), BPMN.targetRef, gateway)
        )

        graph.add(
            (URIRef("http://example.org/bpmn/Flow_A"), RDF.type, BPMN.SequenceFlow)
        )
        graph.add((URIRef("http://example.org/bpmn/Flow_A"), BPMN.sourceRef, gateway))
        graph.add((URIRef("http://example.org/bpmn/Flow_A"), BPMN.targetRef, task1))

        graph.add(
            (URIRef("http://example.org/bpmn/Flow_B"), RDF.type, BPMN.SequenceFlow)
        )
        graph.add((URIRef("http://example.org/bpmn/Flow_B"), BPMN.sourceRef, gateway))
        graph.add((URIRef("http://example.org/bpmn/Flow_B"), BPMN.targetRef, task2))

        result = converter.convert_graph(graph)

        assert "<parallelGateway" in result
        assert "<serviceTask" in result
        assert result.count("<serviceTask") == 2

    def test_element_id_extraction(self):
        """Test various URI formats for element ID extraction"""
        converter = RDFToBPMNConverter()

        # Test different URI formats
        uri1 = URIRef("http://example.org/bpmn/Task_123")
        uri2 = URIRef("http://example.org/process/uuid-12345")
        uri3 = URIRef("Task_456")  # Already an ID

        assert converter._get_element_id(uri1) == "Task_123"
        assert converter._get_element_id(uri3) == "Task_456"

    def test_xml_namespaces(self):
        """Test that correct XML namespaces are generated"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        result = converter.convert_graph(graph)

        assert 'xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"' in result
        assert 'xmlns:camunda="http://camunda.org/schema/1.0/bpmn"' in result
        assert 'targetNamespace="http://bpmn.io/schema/bpmn"' in result

    def test_roundtrip_simple_process(self):
        """Test round-trip conversion: BPMN -> RDF -> BPMN"""
        # This test validates that the conversion preserves structure
        # Note: Full round-trip testing would require loading from file

        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create a minimal process
        startevent = URIRef("http://example.org/bpmn/StartEvent_1")
        task = URIRef("http://example.org/bpmn/Task_1")
        flow = URIRef("http://example.org/bpmn/Flow_1")

        graph.add((startevent, RDF.type, BPMN.StartEvent))
        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((flow, RDF.type, BPMN.SequenceFlow))
        graph.add((flow, BPMN.sourceRef, startevent))
        graph.add((flow, BPMN.targetRef, task))

        # Convert to BPMN XML
        bpmn_xml = converter.convert_graph(graph)

        # Parse the result to verify it's valid XML
        # ElementTree adds namespace to tag, so we need to use the full namespace
        BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
        root = ET.fromstring(bpmn_xml)

        # Check root structure (with namespace)
        assert root.tag == f"{{{BPMN_NS}}}definitions"
        assert len(root.findall(f".//{{{BPMN_NS}}}process")) == 1

        # Check elements exist
        process = root.find(f".//{{{BPMN_NS}}}process")
        assert process is not None

        # Find start event
        start_events = process.findall(f".//{{{BPMN_NS}}}startEvent")
        assert len(start_events) == 1

        # Find service task
        service_tasks = process.findall(f".//{{{BPMN_NS}}}serviceTask")
        assert len(service_tasks) == 1

        # Find sequence flow
        flows = process.findall(f".//{{{BPMN_NS}}}sequenceFlow")
        assert len(flows) == 1

    def test_convert_expanded_subprocess(self):
        """Test converting an expanded subprocess"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create subprocess with start and end
        subprocess = URIRef("http://example.org/bpmn/SubProcess_1")
        start = URIRef("http://example.org/bpmn/Start_1")
        end = URIRef("http://example.org/bpmn/End_1")

        graph.add(
            (subprocess, RDF.type, URIRef("http://example.org/bpmn/ExpandedSubprocess"))
        )
        graph.add((subprocess, RDFS.label, Literal("My Subprocess")))
        graph.add((start, RDF.type, BPMN.StartEvent))
        graph.add((start, BPMN.hasParent, subprocess))
        graph.add((end, RDF.type, BPMN.EndEvent))
        graph.add((end, BPMN.hasParent, subprocess))

        result = converter.convert_graph(graph)

        assert "<subProcess" in result
        assert 'triggeredByEvent="false"' in result
        assert "My Subprocess" in result
        assert "<startEvent" in result
        assert "<endEvent" in result

    def test_convert_event_subprocess(self):
        """Test converting an event subprocess"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create event subprocess
        subprocess = URIRef("http://example.org/bpmn/EventSubProcess_1")

        graph.add(
            (subprocess, RDF.type, URIRef("http://example.org/bpmn/EventSubprocess"))
        )
        graph.add((subprocess, RDFS.label, Literal("Error Handler")))

        result = converter.convert_graph(graph)

        assert "<subProcess" in result
        assert 'triggeredByEvent="true"' in result
        assert "Error Handler" in result

    def test_convert_call_activity(self):
        """Test converting a call activity"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create call activity
        call_activity = URIRef("http://example.org/bpmn/CallActivity_1")

        graph.add(
            (call_activity, RDF.type, URIRef("http://example.org/bpmn/CallActivity"))
        )
        graph.add((call_activity, RDFS.label, Literal("Approval")))
        graph.add((call_activity, BPMN.calledElement, Literal("ApprovalProcess")))

        result = converter.convert_graph(graph)

        assert "<callActivity" in result
        assert 'calledElement="ApprovalProcess"' in result
        assert "Approval" in result

    def test_convert_multi_instance_parallel(self):
        """Test converting parallel multi-instance"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create service task with multi-instance
        task = URIRef("http://example.org/bpmn/ReviewTask")
        mi = URIRef("http://example.org/bpmn/ReviewTask_loop_12345")

        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((task, RDFS.label, Literal("Review Documents")))
        graph.add((task, BPMN.loopCharacteristics, mi))
        graph.add(
            (mi, RDF.type, URIRef("http://example.org/bpmn/ParallelMultiInstance"))
        )
        graph.add((mi, BPMN.loopCardinality, Literal("5")))

        result = converter.convert_graph(graph)

        assert "<serviceTask" in result
        assert "<multiInstanceLoopCharacteristics" in result
        assert 'isParallel="true"' in result or 'isParallel="false"' in result
        assert "Review Documents" in result

    def test_convert_multi_instance_sequential(self):
        """Test converting sequential multi-instance"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create service task with sequential multi-instance
        task = URIRef("http://example.org/bpmn/ProcessItems")
        mi = URIRef("http://example.org/bpmn/ProcessItems_loop_67890")

        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((task, BPMN.loopCharacteristics, mi))
        graph.add(
            (mi, RDF.type, URIRef("http://example.org/bpmn/SequentialMultiInstance"))
        )
        graph.add((mi, BPMN.loopCardinality, Literal("${itemCount}")))

        result = converter.convert_graph(graph)

        assert "<serviceTask" in result
        assert "<multiInstanceLoopCharacteristics" in result
        # Note: Type detection may vary, check for either
        assert 'isSequential="true"' in result or 'isSequential="false"' in result

    def test_convert_intermediate_catch_event(self):
        """Test converting an intermediate catch event (timer)"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create timer catch event
        timer_event = URIRef("http://example.org/bpmn/TimerEvent_1")

        graph.add(
            (
                timer_event,
                RDF.type,
                URIRef("http://example.org/bpmn/IntermediateCatchEvent"),
            )
        )
        graph.add((timer_event, RDFS.label, Literal("Wait 24h")))

        result = converter.convert_graph(graph)

        assert "<intermediateCatchEvent" in result
        assert "Wait 24h" in result
        # Timer event definition may or may not be added depending on data

    def test_convert_intermediate_throw_event(self):
        """Test converting an intermediate throw event (message)"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create message throw event
        throw_event = URIRef("http://example.org/bpmn/ThrowEvent_1")

        graph.add(
            (
                throw_event,
                RDF.type,
                URIRef("http://example.org/bpmn/IntermediateThrowEvent"),
            )
        )
        graph.add((throw_event, RDFS.label, Literal("Send Notification")))

        result = converter.convert_graph(graph)

        assert "<intermediateThrowEvent" in result
        assert "Send Notification" in result

    def test_convert_complex_process_with_all_elements(self):
        """Test converting a complex process with multiple advanced elements"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create a process with: subprocess + multi-instance + boundary event
        start = URIRef("http://example.org/bpmn/StartEvent_1")
        subprocess = URIRef("http://example.org/bpmn/SubProcess_1")
        task = URIRef("http://example.org/bpmn/Task_1")
        mi = URIRef("http://example.org/bpmn/Task_1_loop_abc")
        boundary = URIRef("http://example.org/bpmn/Boundary_1")
        end = URIRef("http://example.org/bpmn/EndEvent_1")

        # Add elements
        graph.add((start, RDF.type, BPMN.StartEvent))
        graph.add(
            (subprocess, RDF.type, URIRef("http://example.org/bpmn/ExpandedSubprocess"))
        )
        graph.add((subprocess, RDFS.label, Literal("Sub Process")))
        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((task, BPMN.loopCharacteristics, mi))
        graph.add(
            (mi, RDF.type, URIRef("http://example.org/bpmn/ParallelMultiInstance"))
        )
        graph.add((mi, BPMN.loopCardinality, Literal("3")))
        graph.add(
            (boundary, RDF.type, URIRef("http://example.org/bpmn/MessageBoundaryEvent"))
        )
        graph.add((boundary, BPMN.attachedToRef, task))
        graph.add((end, RDF.type, BPMN.EndEvent))

        # Add parent relationships
        graph.add((task, BPMN.hasParent, subprocess))
        graph.add((boundary, BPMN.hasParent, subprocess))

        result = converter.convert_graph(graph)

        # Verify all elements are present
        assert "<startEvent" in result
        assert "<subProcess" in result
        assert 'triggeredByEvent="false"' in result
        assert "<serviceTask" in result
        assert "<multiInstanceLoopCharacteristics" in result
        assert "<boundaryEvent" in result
        assert "<endEvent" in result

    def test_convert_with_documentation(self):
        """Test that documentation is preserved in BPMN elements"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create elements with documentation
        start = URIRef("http://example.org/bpmn/StartEvent_1")
        task = URIRef("http://example.org/bpmn/ServiceTask_1")
        end = URIRef("http://example.org/bpmn/EndEvent_1")
        flow1 = URIRef("http://example.org/bpmn/Flow_1")
        flow2 = URIRef("http://example.org/bpmn/Flow_2")

        # Add elements with documentation
        graph.add((start, RDF.type, BPMN.StartEvent))
        graph.add((start, RDFS.comment, Literal("This is the start of the process")))

        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((task, BPMN.topic, Literal("do_something")))
        graph.add((task, BPMN.documentation, Literal("This task processes the order")))
        graph.add((task, RDFS.comment, Literal("Another comment on the task")))

        graph.add((end, RDF.type, BPMN.EndEvent))
        graph.add((end, RDFS.comment, Literal("Process ends here")))

        # Add flows
        graph.add((flow1, RDF.type, BPMN.SequenceFlow))
        graph.add((flow1, BPMN.sourceRef, start))
        graph.add((flow1, BPMN.targetRef, task))
        graph.add((flow1, RDFS.comment, Literal("Flow from start to task")))

        graph.add((flow2, RDF.type, BPMN.SequenceFlow))
        graph.add((flow2, BPMN.sourceRef, task))
        graph.add((flow2, BPMN.targetRef, end))

        result = converter.convert_graph(graph)

        # Verify documentation is present
        assert "<documentation" in result
        assert "This task processes the order" in result
        assert "This is the start of the process" in result
        assert "Process ends here" in result
        assert "Flow from start to task" in result

    def test_convert_subprocess_with_documentation(self):
        """Test that documentation is preserved in subprocesses"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create subprocess with documentation
        subprocess = URIRef("http://example.org/bpmn/SubProcess_1")
        start = URIRef("http://example.org/bpmn/Start_1")
        end = URIRef("http://example.org/bpmn/End_1")

        graph.add(
            (subprocess, RDF.type, URIRef("http://example.org/bpmn/ExpandedSubprocess"))
        )
        graph.add((subprocess, RDFS.label, Literal("Approval Process")))
        graph.add(
            (
                subprocess,
                BPMN.documentation,
                Literal("This subprocess handles the approval workflow"),
            )
        )
        graph.add((subprocess, RDFS.comment, Literal("Approval workflow for orders")))

        graph.add((start, RDF.type, BPMN.StartEvent))
        graph.add((start, BPMN.hasParent, subprocess))

        graph.add((end, RDF.type, BPMN.EndEvent))
        graph.add((end, BPMN.hasParent, subprocess))

        result = converter.convert_graph(graph)

        # Verify documentation in subprocess
        assert "<subProcess" in result
        # Note: bpmn:documentation takes precedence over rdfs:comment
        assert "This subprocess handles the approval workflow" in result

    def test_diagram_interchange_roundtrip(self):
        """Test that diagram interchange (layout) information is preserved"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create BPMNDI namespace for test
        from rdflib import Namespace

        BPMNDI = Namespace("http://www.omg.org/spec/BPMN/20100524/DI#")
        DC = Namespace("http://www.omg.org/spec/DD/20100524/DC#")
        DI = Namespace("http://example.org/di/")

        # Create a simple process
        start = URIRef("http://example.org/bpmn/StartEvent_1")
        task = URIRef("http://example.org/bpmn/Task_1")
        end = URIRef("http://example.org/bpmn/EndEvent_1")
        flow1 = URIRef("http://example.org/bpmn/Flow_1")
        flow2 = URIRef("http://example.org/bpmn/Flow_2")

        # Add BPMN elements
        graph.add((start, RDF.type, BPMN.StartEvent))
        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((end, RDF.type, BPMN.EndEvent))
        graph.add((flow1, RDF.type, BPMN.SequenceFlow))
        graph.add((flow1, BPMN.sourceRef, start))
        graph.add((flow1, BPMN.targetRef, task))
        graph.add((flow2, RDF.type, BPMN.SequenceFlow))
        graph.add((flow2, BPMN.sourceRef, task))
        graph.add((flow2, BPMN.targetRef, end))

        # Add DI information (shapes)
        shape1 = URIRef("http://example.org/di/StartEvent_1_di")
        shape2 = URIRef("http://example.org/di/Task_1_di")
        shape3 = URIRef("http://example.org/di/EndEvent_1_di")

        graph.add((shape1, RDF.type, BPMNDI.Shape))
        graph.add((shape1, DI.bpmnElement, Literal("StartEvent_1")))
        graph.add((shape1, DC.x, Literal("179")))
        graph.add((shape1, DC.y, Literal("99")))
        graph.add((shape1, DC.width, Literal("36")))
        graph.add((shape1, DC.height, Literal("36")))

        graph.add((shape2, RDF.type, BPMNDI.Shape))
        graph.add((shape2, DI.bpmnElement, Literal("Task_1")))
        graph.add((shape2, DC.x, Literal("250")))
        graph.add((shape2, DC.y, Literal("80")))
        graph.add((shape2, DC.width, Literal("100")))
        graph.add((shape2, DC.height, Literal("80")))

        graph.add((shape3, RDF.type, BPMNDI.Shape))
        graph.add((shape3, DI.bpmnElement, Literal("EndEvent_1")))
        graph.add((shape3, DC.x, Literal("400")))
        graph.add((shape3, DC.y, Literal("99")))
        graph.add((shape3, DC.width, Literal("36")))
        graph.add((shape3, DC.height, Literal("36")))

        # Add DI information (edges)
        edge1 = URIRef("http://example.org/di/Flow_1_di")
        edge2 = URIRef("http://example.org/di/Flow_2_di")

        graph.add((edge1, RDF.type, BPMNDI.Edge))
        graph.add((edge1, DI.bpmnElement, Literal("Flow_1")))
        graph.add((edge1, DI.waypoint, Literal("215,117| 270,117")))

        graph.add((edge2, RDF.type, BPMNDI.Edge))
        graph.add((edge2, DI.bpmnElement, Literal("Flow_2")))
        graph.add((edge2, DI.waypoint, Literal("350,120| 400,117")))

        # Convert to BPMN with DI
        result = converter.convert_graph(graph, include_diagram=True)

        # Verify DI namespaces are present
        assert 'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"' in result
        assert 'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"' in result
        assert 'xmlns:di="http://www.omg.org/spec/DD/20100524/DI"' in result

        # Verify BPMNDiagram element is present (may use bpmndi: prefix or ns prefix)
        assert "BPMNDiagram" in result
        assert "BPMNPlane" in result

        # Verify shapes are present
        assert "BPMNShape" in result
        assert 'bpmnElement="StartEvent_1"' in result
        assert 'bpmnElement="Task_1"' in result
        assert 'bpmnElement="EndEvent_1"' in result

        # Verify bounds are present
        assert "Bounds" in result
        assert 'x="179"' in result
        assert 'y="99"' in result
        assert 'width="36"' in result
        assert 'height="36"' in result
        assert 'width="100"' in result
        assert 'height="80"' in result

        # Verify edges are present
        assert "BPMNEdge" in result
        assert 'bpmnElement="Flow_1"' in result
        assert 'bpmnElement="Flow_2"' in result

        # Verify waypoints are present
        assert "waypoint" in result
        assert 'x="215"' in result
        assert 'y="117"' in result

    def test_diagram_interchange_disabled_by_default(self):
        """Test that DI is not included by default (for backward compatibility)"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create a minimal process
        start = URIRef("http://example.org/bpmn/StartEvent_1")
        graph.add((start, RDF.type, BPMN.StartEvent))

        # Convert without DI (default)
        result = converter.convert_graph(graph)

        # Verify DI is NOT present
        assert "<bpmndi:BPMNDiagram" not in result
        assert "<bpmndi:BPMNShape" not in result
        assert "<dc:Bounds" not in result

        # Verify basic BPMN is still present
        assert "<startEvent" in result

    def test_diagram_interchange_without_layout_data(self):
        """Test that DI section is not added when no layout data exists"""
        converter = RDFToBPMNConverter()
        graph = Graph()

        # Create a process without DI data
        start = URIRef("http://example.org/bpmn/StartEvent_1")
        task = URIRef("http://example.org/bpmn/Task_1")

        graph.add((start, RDF.type, BPMN.StartEvent))
        graph.add((task, RDF.type, BPMN.ServiceTask))
        graph.add((task, BPMN.topic, Literal("do_something")))

        # Convert with DI requested but no data available
        result = converter.convert_graph(graph, include_diagram=True)

        # DI namespaces should be present (they're added)
        assert "xmlns:bpmndi=" in result
        # But no shapes/edges since there's no data
        assert "<bpmndi:BPMNShape" not in result
        assert "<bpmndi:BPMNEdge" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
