#!/usr/bin/env python3
"""
Simple test for BPMN parsing issue
"""

import xml.etree.ElementTree as ET

def test_xml_parsing():
    """Test if the XML can be parsed by ElementTree"""
    try:
        tree = ET.parse("test.bpmn")
        root = tree.getroot()
        print("✅ XML parsing successful")
        print(f"   Root tag: {root.tag}")
        print(f"   Root attributes: {root.attrib}")

        # Find the serviceTask
        for elem in root.iter():
            if 'serviceTask' in elem.tag:
                print(f"   Found serviceTask: {elem.tag}")
                print(f"   Attributes: {elem.attrib}")
                break

        return True
    except Exception as e:
        print(f"❌ XML parsing failed: {e}")
        return False

if __name__ == "__main__":
    test_xml_parsing()