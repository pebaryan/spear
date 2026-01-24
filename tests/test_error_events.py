#!/usr/bin/env python3
"""
Comprehensive tests for BPMN Error Handling Features

Tests cover:
- Cancel End Events
- Compensation End Events
- Error End Events
- Error Boundary Events
- Compensation Boundary Events
- Error throwing via API
- Instance cancellation via API
"""

import pytest
import tempfile
import os
from rdflib import Graph, RDF, Literal
from src.conversion import BPMNToRDFConverter, RDFToBPMNConverter
from src.api.storage import RDFStorageService


class TestCancelEndEvent:
    """Test cancel end event parsing and export"""

    def test_cancel_end_event_parsing(self):
        """Test cancel end event is correctly parsed to RDF"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="StartEvent_1" />
    <subProcess id="SubProcess_1" triggeredByEvent="false">
      <startEvent id="SubStart" />
      <serviceTask id="PaymentTask" camunda:topic="process_payment" />
      <cancelEndEvent id="CancelEnd" />
      <sequenceFlow sourceRef="SubStart" targetRef="PaymentTask" />
      <sequenceFlow sourceRef="PaymentTask" targetRef="CancelEnd" />
    </subProcess>
    <endEvent id="EndEvent_1" />
    <sequenceFlow sourceRef="StartEvent_1" targetRef="SubProcess_1" />
    <sequenceFlow sourceRef="SubProcess_1" targetRef="EndEvent_1" />
  </process>
</definitions>"""

        # Parse BPMN to RDF
        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            # Verify RDF has cancel end event
            cancel_found = False
            for s, p, o in graph.triples((None, RDF.type, None)):
                if "cancelendevent" in str(o).lower():
                    cancel_found = True
                    break

            assert cancel_found, "Cancel end event should be in RDF graph"
        finally:
            os.unlink(temp_file)

    def test_cancel_end_event_export(self):
        """Test cancel end event is correctly exported to BPMN XML"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <subProcess id="SubProcess_1" triggeredByEvent="false">
      <cancelEndEvent id="CancelEnd" />
    </subProcess>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            # Convert back to BPMN
            rdf_converter = RDFToBPMNConverter()
            exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

            assert "<cancelEndEvent" in exported_xml
        finally:
            os.unlink(temp_file)


class TestCompensationEndEvent:
    """Test compensation end event parsing and export"""

    def test_compensation_end_event_parsing(self):
        """Test compensation end event is correctly parsed to RDF"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <compensationEndEvent id="CompEnd">
      <compensationEventDefinition compensateRef="UndoOrder" />
    </compensationEndEvent>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            # Verify RDF has compensation end event
            comp_found = False
            for s, p, o in graph.triples((None, RDF.type, None)):
                if "compensationendevent" in str(o).lower():
                    comp_found = True
                    break

            assert comp_found, "Compensation end event should be in RDF graph"
        finally:
            os.unlink(temp_file)

    def test_compensation_end_event_export(self):
        """Test compensation end event is correctly exported to BPMN XML"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <compensationEndEvent id="CompEnd">
      <compensationEventDefinition compensateRef="UndoOrder" />
    </compensationEndEvent>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            rdf_converter = RDFToBPMNConverter()
            exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

            assert "<compensationEndEvent" in exported_xml
            assert "<compensationEventDefinition" in exported_xml
        finally:
            os.unlink(temp_file)


class TestErrorEndEvent:
    """Test error end event parsing and export"""

    def test_error_end_event_parsing(self):
        """Test error end event is correctly parsed to RDF"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <endEvent id="ErrorEnd">
      <errorEventDefinition errorRef="Error_ValidationFailed" />
    </endEvent>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            # Verify RDF has error end event
            error_found = False
            for s, p, o in graph.triples((None, RDF.type, None)):
                if "errorendevent" in str(o).lower():
                    error_found = True
                    break

            assert error_found, "Error end event should be in RDF graph"
        finally:
            os.unlink(temp_file)

    def test_error_end_event_export_with_errorref(self):
        """Test error end event preserves errorRef attribute"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <endEvent id="ErrorEnd">
      <errorEventDefinition errorRef="Error_ValidationFailed" />
    </endEvent>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            rdf_converter = RDFToBPMNConverter()
            exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

            assert "<endEvent" in exported_xml
            assert "<errorEventDefinition" in exported_xml
            assert 'errorRef="Error_ValidationFailed"' in exported_xml
        finally:
            os.unlink(temp_file)


class TestErrorBoundaryEvent:
    """Test error boundary event parsing and export"""

    def test_error_boundary_event_parsing(self):
        """Test error boundary event is correctly parsed to RDF"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <serviceTask id="Task_1" camunda:topic="process_order">
      <boundaryEvent id="ErrorBoundary" attachedToRef="Task_1" cancelActivity="true">
        <errorEventDefinition errorRef="Error_OrderFailed" />
      </boundaryEvent>
    </serviceTask>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            # Verify RDF has error boundary event
            error_boundary_found = False
            for s, p, o in graph.triples((None, RDF.type, None)):
                if "errorboundaryevent" in str(o).lower():
                    error_boundary_found = True
                    break

            assert error_boundary_found, "Error boundary event should be in RDF graph"
        finally:
            os.unlink(temp_file)

    def test_error_boundary_event_interrupting(self):
        """Test error boundary event with interrupting=true"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <serviceTask id="Task_1" camunda:topic="process_order">
      <boundaryEvent id="ErrorBoundary" attachedToRef="Task_1" cancelActivity="true">
        <errorEventDefinition errorRef="Error_OrderFailed" />
      </boundaryEvent>
    </serviceTask>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            rdf_converter = RDFToBPMNConverter()
            exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

            assert "<boundaryEvent" in exported_xml
            assert 'attachedToRef="Task_1"' in exported_xml
            assert 'cancelActivity="true"' in exported_xml
        finally:
            os.unlink(temp_file)


class TestCompensationBoundaryEvent:
    """Test compensation boundary event parsing and export"""

    def test_compensation_boundary_event_parsing(self):
        """Test compensation boundary event is correctly parsed to RDF"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <serviceTask id="Task_1" camunda:topic="process_payment">
      <boundaryEvent id="CompBoundary" attachedToRef="Task_1" cancelActivity="false">
        <compensationEventDefinition compensateRef="RefundPayment" />
      </boundaryEvent>
    </serviceTask>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            # Verify RDF has compensation boundary event
            comp_boundary_found = False
            for s, p, o in graph.triples((None, RDF.type, None)):
                if "compensationboundaryevent" in str(o).lower():
                    comp_boundary_found = True
                    break

            assert comp_boundary_found, (
                "Compensation boundary event should be in RDF graph"
            )
        finally:
            os.unlink(temp_file)

    def test_compensation_boundary_event_non_interrupting(self):
        """Test compensation boundary event with cancelActivity=false"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <serviceTask id="Task_1" camunda:topic="process_payment">
      <boundaryEvent id="CompBoundary" attachedToRef="Task_1" cancelActivity="false">
        <compensationEventDefinition compensateRef="RefundPayment" />
      </boundaryEvent>
    </serviceTask>
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            graph = converter.parse_bpmn_to_graph(temp_file)

            rdf_converter = RDFToBPMNConverter()
            exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

            assert "<boundaryEvent" in exported_xml
            assert 'cancelActivity="false"' in exported_xml
            assert "<compensationEventDefinition" in exported_xml
        finally:
            os.unlink(temp_file)


class TestErrorAPIOperations:
    """Test error handling via API operations"""

    @pytest.fixture
    def storage(self):
        temp_dir = tempfile.mkdtemp()
        storage = RDFStorageService(storage_path=temp_dir)
        yield storage
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_throw_error_nonexistent_instance(self, storage):
        """Test throwing error on nonexistent instance raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            storage.throw_error(instance_id="nonexistent", error_code="TEST_ERROR")
        assert "not found" in str(exc_info.value).lower()

    def test_cancel_instance_nonexistent(self, storage):
        """Test cancelling nonexistent instance raises ValueError"""
        with pytest.raises(ValueError) as exc_info:
            storage.cancel_instance(instance_id="nonexistent")
        assert "not found" in str(exc_info.value).lower()

    def test_throw_error_on_completed_instance(self, storage):
        """Test throwing error on completed instance raises ValueError"""
        # Create a simple process
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             targetNamespace="http://example.org/bpmn">
  <process id="SimpleProcess" isExecutable="true">
    <startEvent id="Start" />
    <endEvent id="End" />
    <sequenceFlow id="Flow1" sourceRef="Start" targetRef="End" />
  </process>
</definitions>"""

        process_id = storage.deploy_process(
            name="Simple Process", description="Test process", bpmn_content=bpmn_xml
        )

        instance = storage.create_instance(process_id)
        instance_id = instance["id"]

        # Instance should complete immediately (start -> end)
        instance_data = storage.get_instance(instance_id)
        assert instance_data["status"] == "COMPLETED"

        # Now try to throw error - should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            storage.throw_error(instance_id=instance_id, error_code="TEST_ERROR")
        assert "cannot throw error" in str(exc_info.value).lower()


class TestErrorEventRoundtrip:
    """Test full roundtrip: BPMN -> RDF -> BPMN for error events"""

    def test_all_error_events_roundtrip(self):
        """Test that all error event types survive roundtrip conversion"""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="Start" />
    
    <serviceTask id="Task1" camunda:topic="do_work">
      <boundaryEvent id="ErrorBoundary" attachedToRef="Task1" cancelActivity="true">
        <errorEventDefinition errorRef="Error_Failed" />
      </boundaryEvent>
    </serviceTask>
    
    <subProcess id="SubProcess_1" triggeredByEvent="false">
      <startEvent id="SubStart" />
      <cancelEndEvent id="CancelEnd" />
    </subProcess>
    
    <endEvent id="ErrorEnd">
      <errorEventDefinition errorRef="Error_Final" />
    </endEvent>
    
    <endEvent id="NormalEnd" />
    
    <sequenceFlow id="Flow1" sourceRef="Start" targetRef="Task1" />
    <sequenceFlow id="Flow2" sourceRef="Task1" targetRef="SubProcess_1" />
    <sequenceFlow id="Flow3" sourceRef="SubProcess_1" targetRef="NormalEnd" />
    <sequenceFlow id="Flow4" sourceRef="ErrorBoundary" targetRef="ErrorEnd" />
  </process>
</definitions>"""

        converter = BPMNToRDFConverter()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
            f.write(bpmn_xml)
            temp_file = f.name

        try:
            # Parse to RDF
            graph = converter.parse_bpmn_to_graph(temp_file)

            # Convert back to BPMN
            rdf_converter = RDFToBPMNConverter()
            exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

            # Verify all elements are present
            assert "<startEvent" in exported_xml
            assert "<serviceTask" in exported_xml
            assert "<boundaryEvent" in exported_xml
            assert "<subProcess" in exported_xml
            assert "<cancelEndEvent" in exported_xml
            assert "<endEvent" in exported_xml
            assert "<errorEventDefinition" in exported_xml
            assert 'errorRef="Error_Failed"' in exported_xml
            assert 'errorRef="Error_Final"' in exported_xml
        finally:
            os.unlink(temp_file)
