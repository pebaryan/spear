#!/usr/bin/env python3
"""
Debug script to test BPMN parsing step by step
"""

import xml.etree.ElementTree as ET

def test_xml_parsing(file_path):
    """Test basic XML parsing"""
    print(f"Testing XML parsing for: {file_path}")
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        print("✅ XML parsing successful")
        return True
    except Exception as e:
        print(f"❌ XML parsing failed: {e}")
        return False

def test_bpmn_converter(file_path):
    """Test the BPMN converter"""
    print(f"\nTesting BPMN converter for: {file_path}")
    try:
        from bpmn2rdf import BPMNToRDFConverter
        converter = BPMNToRDFConverter()
        result = converter.parse_bpmn(file_path)
        print("✅ BPMN conversion successful"        print(f"   Output length: {len(result)} characters")
        return True
    except Exception as e:
        print(f"❌ BPMN conversion failed: {e}")
        return False

if __name__ == "__main__":
    # Test simple BPMN file
    print("=" * 50)
    print("TESTING SIMPLE BPMN FILE")
    print("=" * 50)

    success1 = test_xml_parsing("simple_test.bpmn")
    success2 = test_bpmn_converter("simple_test.bpmn")

    print("\n" + "=" * 50)
    print("TESTING BPMN FILE WITH CAMUNDA EXTENSIONS")
    print("=" * 50)

    success3 = test_xml_parsing("test.bpmn")
    success4 = test_bpmn_converter("test.bpmn")

    print("
RESULTS:")
    print(f"Simple BPMN XML parsing: {'✅' if success1 else '❌'}")
    print(f"Simple BPMN conversion: {'✅' if success2 else '❌'}")
    print(f"Camunda BPMN XML parsing: {'✅' if success3 else '❌'}")
    print(f"Camunda BPMN conversion: {'✅' if success4 else '❌'}")