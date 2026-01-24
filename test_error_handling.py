#!/usr/bin/env python3
"""
Integration test for BPMN Error Handling Features
Tests cancel end events, compensation events, and error end events
"""

from src.conversion import BPMNToRDFConverter, RDFToBPMNConverter
from rdflib import Graph, URIRef, RDF, Literal


def test_cancel_end_event_roundtrip():
    """Test cancel end event parsing and export"""
    print("Testing Cancel End Event...")

    # Create a simple BPMN XML with cancel end event
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
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
        f.write(bpmn_xml)
        temp_file = f.name

    graph = converter.parse_bpmn_to_graph(temp_file)

    # Verify RDF has cancel end event
    cancel_found = False
    for s, p, o in graph.triples((None, RDF.type, None)):
        if "cancelendevent" in str(o).lower():
            cancel_found = True
            print(f"  [OK] Cancel end event found in RDF: {s}")
            break

    assert cancel_found, "Cancel end event should be in RDF graph"

    # Convert back to BPMN
    rdf_converter = RDFToBPMNConverter()
    exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

    # Verify cancel end event in exported XML
    assert "<cancelEndEvent" in exported_xml, (
        "Exported BPMN should contain cancelEndEvent"
    )
    print("  [OK] Cancel end event found in exported BPMN")

    print("[PASS] Cancel End Event test passed!\n")


def test_compensation_end_event_roundtrip():
    """Test compensation end event parsing and export"""
    print("Testing Compensation End Event...")

    bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="StartEvent_1" />
    <subProcess id="SubProcess_1" triggeredByEvent="false">
      <startEvent id="SubStart" />
      <serviceTask id="OrderTask" camunda:topic="create_order" />
      <compensationEndEvent id="CompEnd">
        <compensationEventDefinition compensateRef="UndoOrder" />
      </compensationEndEvent>
      <sequenceFlow sourceRef="SubStart" targetRef="OrderTask" />
      <sequenceFlow sourceRef="OrderTask" targetRef="CompEnd" />
    </subProcess>
    <endEvent id="EndEvent_1" />
    <sequenceFlow sourceRef="StartEvent_1" targetRef="SubProcess_1" />
    <sequenceFlow sourceRef="SubProcess_1" targetRef="EndEvent_1" />
  </process>
</definitions>"""

    # Parse BPMN to RDF
    converter = BPMNToRDFConverter()
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
        f.write(bpmn_xml)
        temp_file = f.name

    graph = converter.parse_bpmn_to_graph(temp_file)

    # Verify RDF has compensation end event
    comp_found = False
    for s, p, o in graph.triples((None, RDF.type, None)):
        if "compensationendevent" in str(o).lower():
            comp_found = True
            print(f"  [OK] Compensation end event found in RDF: {s}")
            break

    assert comp_found, "Compensation end event should be in RDF graph"

    # Convert back to BPMN
    rdf_converter = RDFToBPMNConverter()
    exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

    # Verify compensation end event in exported XML
    assert "<compensationEndEvent" in exported_xml, (
        "Exported BPMN should contain compensationEndEvent"
    )
    assert "<compensationEventDefinition" in exported_xml, (
        "Should have compensationEventDefinition"
    )
    print("  [OK] Compensation end event found in exported BPMN")
    print("  [OK] Compensation event definition found in exported BPMN")

    print("[PASS] Compensation End Event test passed!\n")


def test_error_end_event_roundtrip():
    """Test error end event parsing and export"""
    print("Testing Error End Event...")

    bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="StartEvent_1" />
    <serviceTask id="Task_1" camunda:topic="validate_data" />
    <endEvent id="ErrorEnd">
      <errorEventDefinition errorRef="Error_ValidationFailed" />
    </endEvent>
    <sequenceFlow sourceRef="StartEvent_1" targetRef="Task_1" />
    <sequenceFlow sourceRef="Task_1" targetRef="ErrorEnd" />
  </process>
</definitions>"""

    # Parse BPMN to RDF
    converter = BPMNToRDFConverter()
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
        f.write(bpmn_xml)
        temp_file = f.name

    graph = converter.parse_bpmn_to_graph(temp_file)

    # Verify RDF has error end event
    error_found = False
    for s, p, o in graph.triples((None, RDF.type, None)):
        if "errorendevent" in str(o).lower():
            error_found = True
            print(f"  [OK] Error end event found in RDF: {s}")
            break

    assert error_found, "Error end event should be in RDF graph"

    # Convert back to BPMN
    rdf_converter = RDFToBPMNConverter()
    exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

    # Verify error end event in exported XML
    assert "<endEvent" in exported_xml, "Exported BPMN should contain endEvent"
    assert "<errorEventDefinition" in exported_xml, "Should have errorEventDefinition"
    assert 'errorRef="Error_ValidationFailed"' in exported_xml, "Should have errorRef"
    print("  [OK] Error end event found in exported BPMN")
    print("  [OK] Error event definition found in exported BPMN")
    print("  [OK] Error reference preserved")

    print("[PASS] Error End Event test passed!\n")


def test_compensation_boundary_event_roundtrip():
    """Test compensation boundary event parsing and export"""
    print("Testing Compensation Boundary Event...")

    bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="StartEvent_1" />
    <serviceTask id="Task_1" camunda:topic="process_payment">
      <boundaryEvent id="CompBoundary" attachedToRef="Task_1" cancelActivity="false">
        <compensationEventDefinition compensateRef="RefundPayment" />
      </boundaryEvent>
    </serviceTask>
    <serviceTask id="RefundTask" camunda:topic="refund_payment" />
    <endEvent id="EndEvent_1" />
    <sequenceFlow sourceRef="StartEvent_1" targetRef="Task_1" />
    <sequenceFlow sourceRef="CompBoundary" targetRef="RefundTask" />
    <sequenceFlow sourceRef="Task_1" targetRef="EndEvent_1" />
  </process>
</definitions>"""

    # Parse BPMN to RDF
    converter = BPMNToRDFConverter()
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
        f.write(bpmn_xml)
        temp_file = f.name

    graph = converter.parse_bpmn_to_graph(temp_file)

    # Verify RDF has compensation boundary event
    comp_boundary_found = False
    for s, p, o in graph.triples((None, RDF.type, None)):
        if "compensationboundaryevent" in str(o).lower():
            comp_boundary_found = True
            print(f"  [OK] Compensation boundary event found in RDF: {s}")
            break

    assert comp_boundary_found, "Compensation boundary event should be in RDF graph"

    # Convert back to BPMN
    rdf_converter = RDFToBPMNConverter()
    exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

    # Verify compensation boundary event in exported XML
    assert "<boundaryEvent" in exported_xml, (
        "Exported BPMN should contain boundaryEvent"
    )
    assert 'attachedToRef="Task_1"' in exported_xml, "Should have attachedToRef"
    assert 'cancelActivity="false"' in exported_xml, "Should have cancelActivity=false"
    assert "<compensationEventDefinition" in exported_xml, (
        "Should have compensationEventDefinition"
    )
    print("  [OK] Compensation boundary event found in exported BPMN")
    print("  [OK] Attached to correct activity")
    print("  [OK] Non-interrupting (cancelActivity=false)")

    print("[PASS] Compensation Boundary Event test passed!\n")


def test_error_boundary_event_roundtrip():
    """Test enhanced error boundary event parsing and export"""
    print("Testing Error Boundary Event...")

    bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="StartEvent_1" />
    <serviceTask id="Task_1" camunda:topic="process_order">
      <boundaryEvent id="ErrorBoundary" attachedToRef="Task_1" cancelActivity="true">
        <errorEventDefinition errorRef="Error_OrderFailed" />
      </boundaryEvent>
    </serviceTask>
    <serviceTask id="ErrorHandler" camunda:topic="handle_error" />
    <endEvent id="EndEvent_1" />
    <sequenceFlow sourceRef="StartEvent_1" targetRef="Task_1" />
    <sequenceFlow sourceRef="ErrorBoundary" targetRef="ErrorHandler" />
    <sequenceFlow sourceRef="Task_1" targetRef="EndEvent_1" />
  </process>
</definitions>"""

    # Parse BPMN to RDF
    converter = BPMNToRDFConverter()
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".bpmn", delete=False) as f:
        f.write(bpmn_xml)
        temp_file = f.name

    graph = converter.parse_bpmn_to_graph(temp_file)

    # Verify RDF has error boundary event
    error_boundary_found = False
    for s, p, o in graph.triples((None, RDF.type, None)):
        if "errorboundaryevent" in str(o).lower():
            error_boundary_found = True
            print(f"  [OK] Error boundary event found in RDF: {s}")
            break

    assert error_boundary_found, "Error boundary event should be in RDF graph"

    # Convert back to BPMN
    rdf_converter = RDFToBPMNConverter()
    exported_xml = rdf_converter.convert_graph(graph, include_diagram=False)

    # Verify error boundary event in exported XML
    assert "<boundaryEvent" in exported_xml, (
        "Exported BPMN should contain boundaryEvent"
    )
    assert 'attachedToRef="Task_1"' in exported_xml, "Should have attachedToRef"
    assert 'cancelActivity="true"' in exported_xml, "Should have cancelActivity=true"
    assert "<errorEventDefinition" in exported_xml, "Should have errorEventDefinition"
    assert 'errorRef="Error_OrderFailed"' in exported_xml, "Should have errorRef"
    print("  [OK] Error boundary event found in exported BPMN")
    print("  [OK] Attached to correct activity")
    print("  [OK] Interrupting (cancelActivity=true)")
    print("  [OK] Error code preserved")

    print("[PASS] Error Boundary Event test passed!\n")


def main():
    """Run all error handling tests"""
    print("=" * 60)
    print("BPMN Error Handling Features Integration Tests")
    print("=" * 60)
    print()

    try:
        test_cancel_end_event_roundtrip()
        test_compensation_end_event_roundtrip()
        test_error_end_event_roundtrip()
        test_compensation_boundary_event_roundtrip()
        test_error_boundary_event_roundtrip()

        print("=" * 60)
        print("[PASS] ALL ERROR HANDLING TESTS PASSED!")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
