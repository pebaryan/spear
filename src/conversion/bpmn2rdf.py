#!/usr/bin/env python3
"""
BPMN to RDF Converter
Converts BPMN 2.0 XML files (Camunda 7) to RDF Turtle format or rdflib.Graph
author: Sonnet 4.5

This module provides two main conversion methods:
- parse_bpmn(): Returns RDF triples as Turtle format string
- parse_bpmn_to_graph(): Returns an rdflib.Graph instance for programmatic use
"""

import xml.etree.ElementTree as ET
from typing import Dict, Set
import sys
import argparse
from rdflib import Graph

class BPMNToRDFConverter:
    def __init__(self):
        # Define namespaces
        self.namespaces = {
            'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
            'bpmndi': 'http://www.omg.org/spec/BPMN/20100524/DI',
            'dc': 'http://www.omg.org/spec/DD/20100524/DC',
            'di': 'http://www.omg.org/spec/DD/20100524/DI',
            'camunda': 'http://camunda.org/schema/1.0/bpmn',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }
        
        # RDF namespaces
        self.rdf_namespaces = {
            'bpmn': 'http://dkm.fbk.eu/index.php/BPMN2_Ontology#',
            'camunda': 'http://camunda.org/schema/1.0/bpmn#',
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
            'xsd': 'http://www.w3.org/2001/XMLSchema#'
        }
        
        self.triples = []
        self.uri_base = "http://example.org/bpmn/"
        
    def parse_bpmn(self, file_path: str) -> str:
        """Parse BPMN XML file and convert to RDF Turtle format"""
        # Register namespaces for parsing BEFORE parsing the file
        for prefix, uri in self.namespaces.items():
            ET.register_namespace(prefix, uri)

        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Start building RDF
        self.triples = []
        self._add_prefixes()
        
        # Process all BPMN elements
        self._process_element(root, None)
        
        return '\n'.join(self.triples)

    def parse_bpmn_to_graph(self, file_path: str) -> Graph:
        """Parse BPMN XML file and return an rdflib.Graph instance

        This method wraps parse_bpmn() and parses the resulting Turtle string
        into an rdflib.Graph for programmatic use.

        Args:
            file_path: Path to the BPMN XML file

        Returns:
            rdflib.Graph containing the parsed BPMN model as RDF triples

        Example:
            converter = BPMNToRDFConverter()
            graph = converter.parse_bpmn_to_graph("process.bpmn")

            # Query the graph
            for s, p, o in graph:
                print(f"{s} {p} {o}")
        """
        # Get the Turtle string from the existing parse_bpmn method
        turtle_data = self.parse_bpmn(file_path)

        # Parse the Turtle string into an rdflib.Graph
        graph = Graph()
        graph.parse(data=turtle_data, format='turtle')

        return graph

    def _add_prefixes(self):
        """Add RDF namespace prefixes"""
        for prefix, uri in self.rdf_namespaces.items():
            self.triples.append(f"@prefix {prefix}: <{uri}> .")
        self.triples.append("")
    
    def _get_uri(self, element_id: str) -> str:
        """Generate URI for an element"""
        return f"<{self.uri_base}{element_id}>"
    
    def _get_tag_name(self, tag: str) -> str:
        """Extract tag name from qualified name"""
        if '}' in tag:
            # Handle namespaced tags like {http://www.omg.org/spec/BPMN/20100524/MODEL}process
            namespace_uri = tag.split('}')[0][1:]  # Remove { and }
            local_name = tag.split('}')[1]
            # Check if this is a BPMN namespace
            if namespace_uri == self.namespaces.get('bpmn'):
                return local_name
            return local_name  # Return local name for other namespaces too
        return tag
    
    def _process_element(self, element, parent_uri):
        """Process XML element and convert to RDF triples"""
        tag_name = self._get_tag_name(element.tag)
        
        # Skip certain elements
        if tag_name in ['definitions', 'BPMNDiagram', 'BPMNPlane', 'BPMNShape', 'BPMNEdge']:
            for child in element:
                self._process_element(child, parent_uri)
            return
        
        # Get element ID
        element_id = element.get('id')
        if not element_id:
            # Generate ID for elements without one
            element_id = f"{tag_name}_{id(element)}"
        
        element_uri = self._get_uri(element_id)
        
        # Add type triple
        self.triples.append(f"{element_uri} rdf:type bpmn:{tag_name} .")
        
        # Process attributes
        for attr_name, attr_value in element.attrib.items():
            if attr_name == 'id':
                continue
                
            # Handle namespaced attributes
            if '}' in attr_name:
                ns, local_name = attr_name.split('}')
                ns = ns[1:]  # Remove leading {
                
                # Find namespace prefix
                ns_prefix = None
                for prefix, uri in self.namespaces.items():
                    if uri == ns:
                        ns_prefix = prefix
                        break
                
                if ns_prefix == 'camunda':
                    self.triples.append(
                        f'{element_uri} camunda:{local_name} "{self._escape_string(attr_value)}" .'
                    )
                else:
                    self.triples.append(
                        f'{element_uri} bpmn:{local_name} "{self._escape_string(attr_value)}" .'
                    )
            else:
                # Handle references to other elements
                if attr_name in ['sourceRef', 'targetRef', 'processRef', 'calledElement']:
                    self.triples.append(
                        f"{element_uri} bpmn:{attr_name} {self._get_uri(attr_value)} ."
                    )
                elif attr_name == 'name':
                    self.triples.append(
                        f'{element_uri} bpmn:name "{self._escape_string(attr_value)}" .'
                    )
                else:
                    self.triples.append(
                        f'{element_uri} bpmn:{attr_name} "{self._escape_string(attr_value)}" .'
                    )
        
        # Add parent relationship if exists
        if parent_uri:
            self.triples.append(f"{element_uri} bpmn:hasParent {parent_uri} .")
        
        # Process child elements
        for child in element:
            child_tag = self._get_tag_name(child.tag)
            
            # Handle special elements
            if child_tag == 'extensionElements':
                self._process_extension_elements(child, element_uri)
            elif child_tag == 'documentation':
                doc_text = child.text if child.text else ""
                self.triples.append(
                    f'{element_uri} bpmn:documentation "{self._escape_string(doc_text)}" .'
                )
            elif child_tag in ['incoming', 'outgoing']:
                ref = child.text.strip() if child.text else ""
                if ref:
                    self.triples.append(
                        f"{element_uri} bpmn:{child_tag} {self._get_uri(ref)} ."
                    )
            elif child_tag == 'conditionExpression':
                expr = child.text if child.text else ""
                self.triples.append(
                    f'{element_uri} bpmn:conditionExpression "{self._escape_string(expr)}" .'
                )
            else:
                self._process_element(child, element_uri)
        
        self.triples.append("")  # Empty line for readability
    
    def _process_extension_elements(self, element, parent_uri):
        """Process Camunda extension elements"""
        for child in element:
            tag_name = self._get_tag_name(child.tag)
            
            # Handle different Camunda extensions
            if 'camunda.org' in child.tag or tag_name.startswith('camunda'):
                extension_uri = f"{parent_uri}_ext_{tag_name}_{id(child)}"
                self.triples.append(f"{extension_uri} rdf:type camunda:{tag_name} .")
                self.triples.append(f"{parent_uri} bpmn:hasExtension {extension_uri} .")
                
                # Process attributes
                for attr_name, attr_value in child.attrib.items():
                    if '}' in attr_name:
                        ns, local_name = attr_name.split('}')
                        self.triples.append(
                            f'{extension_uri} camunda:{local_name} "{self._escape_string(attr_value)}" .'
                        )
                    else:
                        self.triples.append(
                            f'{extension_uri} camunda:{attr_name} "{self._escape_string(attr_value)}" .'
                        )
                
                # Process nested elements
                for nested in child:
                    nested_tag = self._get_tag_name(nested.tag)
                    nested_uri = f"{extension_uri}_{nested_tag}_{id(nested)}"
                    self.triples.append(f"{nested_uri} rdf:type camunda:{nested_tag} .")
                    self.triples.append(f"{extension_uri} camunda:has{nested_tag.capitalize()} {nested_uri} .")
                    
                    for attr_name, attr_value in nested.attrib.items():
                        if '}' in attr_name:
                            ns, local_name = attr_name.split('}')
                            self.triples.append(
                                f'{nested_uri} camunda:{local_name} "{self._escape_string(attr_value)}" .'
                            )
                        else:
                            self.triples.append(
                                f'{nested_uri} camunda:{attr_name} "{self._escape_string(attr_value)}" .'
                            )
    
    def _escape_string(self, s: str) -> str:
        """Escape string for RDF Turtle format"""
        s = s.replace('\\', '\\\\')
        s = s.replace('"', '\\"')
        s = s.replace('\n', '\\n')
        s = s.replace('\r', '\\r')
        s = s.replace('\t', '\\t')
        return s


def main():
    parser = argparse.ArgumentParser(
        description='Convert BPMN 2.0 XML files to RDF Turtle format'
    )
    parser.add_argument('input_file', help='Input BPMN XML file')
    parser.add_argument('-o', '--output', help='Output Turtle file (default: stdout)')
    
    args = parser.parse_args()
    
    try:
        converter = BPMNToRDFConverter()
        rdf_output = converter.parse_bpmn(args.input_file)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(rdf_output)
            print(f"RDF output written to {args.output}")
        else:
            print(rdf_output)
            
    except FileNotFoundError:
        print(f"Error: File '{args.input_file}' not found", file=sys.stderr)
        sys.exit(1)
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()