#!/usr/bin/env python3
"""
Quick test to check if the XML parsing works now
"""

import xml.etree.ElementTree as ET

def test_xml():
    try:
        tree = ET.parse("test.bpmn")
        root = tree.getroot()
        print("✅ XML parsing successful!")
        print(f"Root tag: {root.tag}")

        # Find the serviceTask
        for elem in root.iter():
            if 'serviceTask' in elem.tag or 'serviceTask' in str(elem.tag):
                print(f"Found serviceTask: {elem.tag}")
                print(f"Attributes: {elem.attrib}")
                break

        return True
    except Exception as e:
        print(f"❌ XML parsing failed: {e}")
        return False

if __name__ == "__main__":
    test_xml()