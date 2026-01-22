#!/usr/bin/env python3
"""
Integration test for RDF to BPMN export feature
Demonstrates the full workflow: Deploy a process -> Export to BPMN
"""

from src.conversion import BPMNToRDFConverter, RDFToBPMNConverter
from src.api.storage import RDFStorageService


def test_roundtrip_deploy_and_export():
    """Test deploying a BPMN file and then exporting it back"""

    # Sample BPMN XML
    bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
             id="Definitions_1"
             targetNamespace="http://example.org/bpmn">
  <process id="TestProcess" isExecutable="true">
    <startEvent id="StartEvent_1" name="Start">
      <outgoing>Flow_1</outgoing>
    </startEvent>
    <serviceTask id="Task_1" name="Process Order" camunda:topic="process_order">
      <incoming>Flow_1</incoming>
      <outgoing>Flow_2</outgoing>
    </serviceTask>
    <userTask id="Task_2" name="Review" camunda:assignee="manager">
      <incoming>Flow_2</incoming>
      <outgoing>Flow_3</outgoing>
    </userTask>
    <endEvent id="EndEvent_1" name="End">
      <incoming>Flow_3</incoming>
    </endEvent>
    <sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_1" />
    <sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="Task_2" />
    <sequenceFlow id="Flow_3" sourceRef="Task_2" targetRef="EndEvent_1" />
  </process>
</definitions>"""

    print("1. Deploying process to storage...")
    storage = RDFStorageService()

    process_id = storage.deploy_process(
        name="Test Process",
        description="A test process for round-trip conversion",
        bpmn_content=bpmn_xml,
        version="1.0.0",
    )
    print(f"   Process deployed with ID: {process_id}")

    print("\n2. Exporting process to BPMN XML...")
    converter = RDFToBPMNConverter()
    exported_xml = converter.convert(process_id, storage)
    print(f"   Exported BPMN XML ({len(exported_xml)} characters)")

    print("\n3. Sample of exported XML:")
    print("   " + "\n   ".join(exported_xml.split("\n")[:15]))
    print("   ...")

    print("\n4. Verifying exported structure...")
    assert "<startEvent" in exported_xml
    assert "<serviceTask" in exported_xml
    assert "<userTask" in exported_xml
    assert "<endEvent" in exported_xml
    assert "<sequenceFlow" in exported_xml
    assert 'camunda:topic="process_order"' in exported_xml
    assert 'camunda:assignee="manager"' in exported_xml
    print("   [OK] All expected elements found")

    print("\n5. Listing all deployed processes...")
    processes = storage.list_processes()
    print(f"   Total processes: {processes['total']}")
    for proc in processes["processes"]:
        print(f"   - {proc['name']} ({proc['id']})")

    print("\n[SUCCESS] Round-trip test successful!")
    print(f"\nYou can also test the API endpoint:")
    print(f"   GET /api/v1/processes/{process_id}/bpmn")

    return process_id, exported_xml


if __name__ == "__main__":
    test_roundtrip_deploy_and_export()
