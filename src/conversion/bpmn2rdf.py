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
import re
from rdflib import Graph, RDF, RDFS, URIRef, Literal, Namespace


class BPMNToRDFConverter:
    def __init__(self):
        # Define namespaces
        self.namespaces = {
            "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
            "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
            "dc": "http://www.omg.org/spec/DD/20100524/DC",
            "di": "http://www.omg.org/spec/DD/20100524/DI",
            "camunda": "http://camunda.org/schema/1.0/bpmn",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        }

        # RDF namespaces
        self.rdf_namespaces = {
            "bpmn": "http://dkm.fbk.eu/index.php/BPMN2_Ontology#",
            "camunda": "http://camunda.org/schema/1.0/bpmn#",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "di": "http://example.org/di/",
            "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI#",
            "dc": "http://www.omg.org/spec/DD/20100524/DC#",
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

        # Extract and store diagram interchange (layout) information
        self._extract_diagram_interchange(root)

        return "\n".join(self.triples)

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
        graph.parse(data=turtle_data, format="turtle")

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
        if "}" in tag:
            # Handle namespaced tags like {http://www.omg.org/spec/BPMN/20100524/MODEL}process
            namespace_uri = tag.split("}")[0][1:]  # Remove { and }
            local_name = tag.split("}")[1]
            # Check if this is a BPMN namespace
            if namespace_uri == self.namespaces.get("bpmn"):
                return local_name
            return local_name  # Return local name for other namespaces too
        return tag

    def _process_element(self, element, parent_uri):
        """Process XML element and convert to RDF triples"""
        tag_name = self._get_tag_name(element.tag)

        # Skip certain elements
        if tag_name in [
            "definitions",
            "BPMNDiagram",
            "BPMNPlane",
            "BPMNShape",
            "BPMNEdge",
        ]:
            for child in element:
                self._process_element(child, parent_uri)
            return

        # Get element ID
        element_id = element.get("id")
        if not element_id:
            # Generate ID for elements without one
            element_id = f"{tag_name}_{id(element)}"

        element_uri = self._get_uri(element_id)

        # Add type triple
        self.triples.append(f"{element_uri} rdf:type bpmn:{tag_name} .")

        source_ref = None
        target_ref = None

        # Process attributes
        for attr_name, attr_value in element.attrib.items():
            if attr_name == "id":
                continue

            # Handle namespaced attributes
            if "}" in attr_name:
                ns, local_name = attr_name.split("}")
                ns = ns[1:]  # Remove leading {

                # Skip camunda:expression on conditionExpression elements
                if (
                    ns == "http://camunda.org/schema/1.0/bpmn"
                    and local_name == "expression"
                ):
                    # This will be handled in _process_condition_expression
                    continue

                # Find namespace prefix
                ns_prefix = None
                for prefix, uri in self.namespaces.items():
                    if uri == ns:
                        ns_prefix = prefix
                        break

                if ns_prefix == "camunda":
                    # Special case: camunda:default should be a URI reference, not a string
                    if local_name == "default":
                        self.triples.append(
                            f"{element_uri} camunda:default {self._get_uri(attr_value)} ."
                        )
                    else:
                        self.triples.append(
                            f'{element_uri} camunda:{local_name} "{self._escape_string(attr_value)}" .'
                        )
                else:
                    self.triples.append(
                        f'{element_uri} bpmn:{local_name} "{self._escape_string(attr_value)}" .'
                    )
            else:
                # Handle references to other elements
                if attr_name in [
                    "sourceRef",
                    "targetRef",
                    "processRef",
                    "calledElement",
                    "attachedToRef",
                ]:
                    self.triples.append(
                        f"{element_uri} bpmn:{attr_name} {self._get_uri(attr_value)} ."
                    )
                    if attr_name == "sourceRef":
                        source_ref = attr_value
                    elif attr_name == "targetRef":
                        target_ref = attr_value
                elif attr_name == "name":
                    self.triples.append(
                        f'{element_uri} bpmn:name "{self._escape_string(attr_value)}" .'
                    )
                elif attr_name == "default":
                    # Store default flow reference for gateways
                    self.triples.append(
                        f"{element_uri} bpmn:default {self._get_uri(attr_value)} ."
                    )
                else:
                    self.triples.append(
                        f'{element_uri} bpmn:{attr_name} "{self._escape_string(attr_value)}" .'
                    )

        # For sequenceFlow elements, add outgoing/incoming references to source/target nodes
        if tag_name == "sequenceFlow" and source_ref and target_ref:
            source_uri = self._get_uri(source_ref)
            target_uri = self._get_uri(target_ref)
            self.triples.append(f"{source_uri} bpmn:outgoing {element_uri} .")
            self.triples.append(f"{target_uri} bpmn:incoming {element_uri} .")

        # Add parent relationship if exists
        if parent_uri:
            self.triples.append(f"{element_uri} bpmn:hasParent {parent_uri} .")

        # Process child elements
        for child in element:
            child_tag = self._get_tag_name(child.tag)

            # Handle special elements
            if child_tag == "extensionElements":
                self._process_extension_elements(child, element_uri)
            elif child_tag == "documentation":
                doc_text = child.text if child.text else ""
                self.triples.append(
                    f'{element_uri} bpmn:documentation "{self._escape_string(doc_text)}" .'
                )
            elif child_tag in ["incoming", "outgoing"]:
                ref = child.text.strip() if child.text else ""
                if ref:
                    self.triples.append(
                        f"{element_uri} bpmn:{child_tag} {self._get_uri(ref)} ."
                    )
            elif child_tag == "conditionExpression":
                # Process condition expression with full details
                self._process_condition_expression(child, element_uri)
            elif tag_name == "endEvent":
                for nested in element:
                    nested_tag = self._get_tag_name(nested.tag)
                    if nested_tag == "messageEventDefinition":
                        self.triples.append(
                            f"{element_uri} rdf:type <http://example.org/bpmn/MessageEndEvent> ."
                        )
                        message_ref = nested.get("messageRef", "")
                        if message_ref:
                            self.triples.append(
                                f"{element_uri} bpmn:messageRef <{message_ref}> ."
                            )
                        camunda_message = nested.get(
                            "{http://camunda.org/schema/1.0/bpmn}message", ""
                        )
                        if camunda_message:
                            self.triples.append(
                                f'{element_uri} camunda:message "{self._escape_string(camunda_message)}" .'
                            )
            elif child_tag == "outgoing":
                ref = child.text.strip() if child.text else ""
                if ref:
                    self.triples.append(
                        f"{element_uri} bpmn:outgoing {self._get_uri(ref)} ."
                    )
            elif child_tag == "incoming":
                ref = child.text.strip() if child.text else ""
                if ref:
                    self.triples.append(
                        f"{element_uri} bpmn:incoming {self._get_uri(ref)} ."
                    )
            elif child_tag == "multiInstanceLoopCharacteristics":
                import uuid

                mi_uuid = str(uuid.uuid4())[:8]
                node_name = element_uri.split("/")[-1].strip("<>")
                mi_uri = f"<http://example.org/bpmn/{node_name}_loop_{mi_uuid}>"
                is_parallel = child.get("isParallel", "false").lower() == "true"
                is_sequential = child.get("isSequential", "false").lower() == "true"

                self.triples.append(
                    f"{mi_uri} rdf:type <http://example.org/bpmn/MultiInstanceLoopCharacteristics> ."
                )
                self.triples.append(
                    f"{element_uri} bpmn:loopCharacteristics {mi_uri} ."
                )

                if is_parallel:
                    self.triples.append(
                        f"{mi_uri} rdf:type <http://example.org/bpmn/ParallelMultiInstance> ."
                    )
                if is_sequential:
                    self.triples.append(
                        f"{mi_uri} rdf:type <http://example.org/bpmn/SequentialMultiInstance> ."
                    )

                for nested in child:
                    nested_tag = self._get_tag_name(nested.tag)
                    if nested_tag == "loopCardinality":
                        cardinality = nested.text.strip() if nested.text else ""
                        if cardinality:
                            self.triples.append(
                                f'{mi_uri} bpmn:loopCardinality "{self._escape_string(cardinality)}" .'
                            )
                    elif nested_tag == "completionCondition":
                        condition = nested.text.strip() if nested.text else ""
                        if condition:
                            self.triples.append(
                                f'{mi_uri} bpmn:completionCondition "{self._escape_string(condition)}" .'
                            )
                    elif nested_tag == "dataInput":
                        data_input = nested.text.strip() if nested.text else ""
                        if data_input:
                            self.triples.append(
                                f'{mi_uri} bpmn:dataInput "{self._escape_string(data_input)}" .'
                            )
                    elif nested_tag == "dataOutput":
                        data_output = nested.text.strip() if nested.text else ""
                        if data_output:
                            self.triples.append(
                                f'{mi_uri} bpmn:dataOutput "{self._escape_string(data_output)}" .'
                            )
            elif tag_name in ["intermediateCatchEvent", "intermediateThrowEvent"]:
                attached_to_ref = element.get("attachedToRef", "")
                if attached_to_ref:
                    self.triples.append(
                        f"{element_uri} rdf:type <http://example.org/bpmn/BoundaryEvent> ."
                    )
                    self.triples.append(
                        f"{element_uri} bpmn:attachedToRef <{attached_to_ref}> ."
                    )
                    attached_uri = self._get_uri(attached_to_ref)
                    self.triples.append(
                        f"{attached_uri} bpmn:hasBoundaryEvent {element_uri} ."
                    )

                    is_interrupting = (
                        element.get("cancelActivity", "true").lower() == "true"
                    )
                    self.triples.append(
                        f'{element_uri} bpmn:interrupting "{str(is_interrupting).lower()}" .'
                    )

                for child in element:
                    child_tag = self._get_tag_name(child.tag)
                    if child_tag == "messageEventDefinition":
                        self.triples.append(
                            f"{element_uri} rdf:type <http://example.org/bpmn/MessageBoundaryEvent> ."
                        )
                        message_ref = child.get("messageRef", "")
                        if message_ref:
                            self.triples.append(
                                f"{element_uri} bpmn:messageRef <{message_ref}> ."
                            )
                        camunda_message = child.get(
                            "{http://camunda.org/schema/1.0/bpmn}message", ""
                        )
                        if camunda_message:
                            self.triples.append(
                                f'{element_uri} camunda:message "{self._escape_string(camunda_message)}" .'
                            )
                    elif child_tag == "timerEventDefinition":
                        self.triples.append(
                            f"{element_uri} rdf:type <http://example.org/bpmn/TimerBoundaryEvent> ."
                        )
                    elif child_tag == "errorEventDefinition":
                        self.triples.append(
                            f"{element_uri} rdf:type <http://example.org/bpmn/ErrorBoundaryEvent> ."
                        )
                    elif child_tag == "signalEventDefinition":
                        self.triples.append(
                            f"{element_uri} rdf:type <http://example.org/bpmn/SignalBoundaryEvent> ."
                        )

            elif tag_name == "subProcess":
                # Handle expanded (embedded) subprocess
                triggered_by_event = (
                    element.get("triggeredByEvent", "false").lower() == "true"
                )

                if triggered_by_event:
                    # Event subprocess
                    self.triples.append(
                        f"{element_uri} rdf:type <http://example.org/bpmn/EventSubprocess> ."
                    )
                    self.triples.append(f'{element_uri} bpmn:triggeredByEvent "true" .')
                else:
                    # Expanded subprocess
                    self.triples.append(
                        f"{element_uri} rdf:type <http://example.org/bpmn/ExpandedSubprocess> ."
                    )

                # Process all child elements of the subprocess
                for child in element:
                    self._process_element(child, element_uri)

            elif tag_name == "callActivity":
                # Handle call activity (collapsed subprocess)
                called_element = element.get("calledElement", "")

                self.triples.append(
                    f"{element_uri} rdf:type <http://example.org/bpmn/CallActivity> ."
                )

                if called_element:
                    self.triples.append(
                        f"{element_uri} bpmn:calledElement <{called_element}> ."
                    )

                # Process child elements if any
                for child in element:
                    self._process_element(child, element_uri)
            else:
                self._process_element(child, element_uri)

        self.triples.append("")  # Empty line for readability

    def _process_extension_elements(self, element, parent_uri):
        """Process Camunda extension elements"""
        for child in element:
            tag_name = self._get_tag_name(child.tag)

            # Handle different Camunda extensions
            if "camunda.org" in child.tag or tag_name.startswith("camunda"):
                extension_uri = f"{parent_uri}_ext_{tag_name}_{id(child)}"
                self.triples.append(f"{extension_uri} rdf:type camunda:{tag_name} .")
                self.triples.append(f"{parent_uri} bpmn:hasExtension {extension_uri} .")

                # Process attributes
                for attr_name, attr_value in child.attrib.items():
                    if "}" in attr_name:
                        ns, local_name = attr_name.split("}")
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
                    self.triples.append(
                        f"{extension_uri} camunda:has{nested_tag.capitalize()} {nested_uri} ."
                    )

                    for attr_name, attr_value in nested.attrib.items():
                        if "}" in attr_name:
                            ns, local_name = attr_name.split("}")
                            self.triples.append(
                                f'{nested_uri} camunda:{local_name} "{self._escape_string(attr_value)}" .'
                            )
                        else:
                            self.triples.append(
                                f'{nested_uri} camunda:{attr_name} "{self._escape_string(attr_value)}" .'
                            )

    def _process_condition_expression(self, element, flow_uri):
        """Process conditionExpression element and store in standardized format

        Stores conditions in a format that can be easily evaluated:
        - bpmn:conditionType: The expression type (camunda:expression, tFormalExpression, etc.)
        - bpmn:conditionBody: The actual expression text
        - bpmn:conditionQuery: Pre-formatted SPARQL ASK query (optional, for complex conditions)
        """
        # Get expression type from xsi:type attribute
        expr_type = element.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")

        # Get expression text from element text
        expr_text = element.text if element.text else ""

        # Also check for camunda:expression attribute on the element
        camunda_expr = element.get("{http://camunda.org/schema/1.0/bpmn}expression", "")

        # If camunda:expression attribute exists, use it
        if camunda_expr:
            expr_text = camunda_expr
            expr_type = "camunda:expression"

        # Store expression type
        if expr_type:
            self.triples.append(
                f'{flow_uri} bpmn:conditionType "{self._escape_string(expr_type)}" .'
            )

        # Store expression body
        if expr_text:
            self.triples.append(
                f'{flow_uri} bpmn:conditionBody "{self._escape_string(expr_text.strip())}" .'
            )

        # Convert camunda:expression to SPARQL ASK query for evaluation
        if "camunda:expression" in expr_type or "camunda" in expr_text:
            sparql_query = self._convert_camunda_to_sparql(expr_text)
            if sparql_query:
                self.triples.append(
                    f'{flow_uri} bpmn:conditionQuery """{sparql_query}""" .'
                )
        else:
            # For other expression types, store as-is for custom evaluation
            self.triples.append(
                f'{flow_uri} bpmn:conditionQuery """ASK {{ ?instance ?variable ?value }}""" .'
            )

        # Store expression body
        if expr_text:
            self.triples.append(
                f'{flow_uri} bpmn:conditionBody "{self._escape_string(expr_text.strip())}" .'
            )

        # Convert camunda:expression to SPARQL ASK query for evaluation
        if "camunda:expression" in expr_type or "camunda" in expr_text:
            sparql_query = self._convert_camunda_to_sparql(expr_text)
            if sparql_query:
                self.triples.append(
                    f'{flow_uri} bpmn:conditionQuery """{sparql_query}""" .'
                )
        else:
            # For other expression types, store as-is for custom evaluation
            self.triples.append(
                f'{flow_uri} bpmn:conditionQuery """ASK {{ ?instance ?variable ?value }}""" .'
            )

    def _convert_camunda_to_sparql(self, expression: str) -> str:
        """Convert Camunda expression to SPARQL ASK query

        Examples:
        - "${amount > 1000}" or "${amount gt 1000}" -> "ASK { ?instance var:amount ?amount . FILTER(?amount > 1000) }"
        - "${approved == true}" -> "ASK { ?instance var:approved ?approved . FILTER(?approved = 'true') }"
        - "${amount <= 1000}" or "${amount lte 1000}" -> "ASK { ?instance var:amount ?amount . FILTER(?amount <= 1000) }"
        """
        if not expression:
            return ""

        # Remove ${} wrapper
        expr = expression.strip()
        if expr.startswith("${") and expr.endswith("}"):
            expr = expr[2:-1]

        # Parse simple expressions like "variable operator value"
        # Match longer operators first (gte, lte, neq, eq, then single chars)
        match = re.match(
            r"(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|>|>=|<=|<|!=|=)\s*(.+)", expr
        )

        if match:
            var_name = match.group(1)
            operator = match.group(2)
            value = match.group(3).strip()

            # Convert operator to SPARQL format
            op_map = {
                ">": ">",
                "gt": ">",
                ">=": ">=",
                "gte": ">=",
                "<": "<",
                "lt": "<",
                "<=": "<=",
                "lte": "<=",
                "==": "=",
                "eq": "=",
                "!=": "!=",
                "neq": "!=",
            }
            sparql_op = op_map.get(operator, operator)

            # Format value as string literal for comparison
            if value.lower() in ("true", "false"):
                # Convert boolean to string literal
                sparql_value = f'"{value.lower()}"'
            elif value.startswith('"') and value.endswith('"'):
                # Already a string literal
                sparql_value = value
            elif re.match(r"^-?\d+\.?\d*$", value):
                # Numeric literal - keep as is
                sparql_value = value
            else:
                # Variable reference or other - wrap in same ASK
                return f"ASK {{ ?instance var:{var_name} ?{var_name} . FILTER(?{var_name} {sparql_op} {value}) }}"

            return f"ASK {{ ?instance var:{var_name} ?v . FILTER(?v {sparql_op} {sparql_value}) }}"

        # For complex expressions, return empty and let custom handler deal with it
        return ""

    def _escape_string(self, s: str) -> str:
        """Escape string for RDF Turtle format"""
        s = s.replace("\\", "\\\\")
        s = s.replace('"', '\\"')
        s = s.replace("\n", "\\n")
        s = s.replace("\r", "\\r")
        s = s.replace("\t", "\\t")
        return s

    def _extract_diagram_interchange(self, root: ET.Element):
        """Extract and store BPMN Diagram Interchange (layout) information.

        This method extracts visual layout information from the BPMN DI section
        and stores it as RDF triples for later reconstruction.
        """
        # Define namespace prefixes
        bpmndi_ns = "http://www.omg.org/spec/BPMN/20100524/DI"
        dc_ns = "http://www.omg.org/spec/DD/20100524/DC"
        di_ns = "http://www.omg.org/spec/DD/20100524/DI"

        # Define RDF namespaces for storing DI info
        DI = Namespace("http://example.org/di/")
        DC = Namespace("http://www.omg.org/spec/DD/20100524/DC#")

        # Find all BPMNDiagram elements
        for diagram in root.findall(f".//{{{bpmndi_ns}}}BPMNDiagram"):
            # Find all shapes (element positions)
            for shape in diagram.findall(f".//{{{bpmndi_ns}}}BPMNShape"):
                shape_id = shape.get("id")
                bpmn_element = shape.get("bpmnElement")

                # Get bounds
                bounds = shape.find(f"{{{dc_ns}}}Bounds")
                if bounds is not None:
                    x = bounds.get("x")
                    y = bounds.get("y")
                    width = bounds.get("width")
                    height = bounds.get("height")

                    # Add RDF triple for bounds
                    di_uri = f"<http://example.org/di/{shape_id}>"
                    self.triples.append(
                        f"{di_uri} a <http://www.omg.org/spec/BPMN/20100524/DI#BPMNShape> ."
                    )
                    self.triples.append(
                        f'{di_uri} <{DI}bpmnElement> "{bpmn_element}" .'
                    )
                    self.triples.append(f'{di_uri} <{DC}x> "{x}" .')
                    self.triples.append(f'{di_uri} <{DC}y> "{y}" .')
                    self.triples.append(f'{di_uri} <{DC}width> "{width}" .')
                    self.triples.append(f'{di_uri} <{DC}height> "{height}" .')

            # Find all edges (flow waypoints)
            for edge in diagram.findall(f".//{{{bpmndi_ns}}}BPMNEdge"):
                edge_id = edge.get("id")
                bpmn_element = edge.get("bpmnElement")

                # Collect waypoints
                waypoints = []
                for waypoint in edge.findall(f"{{{di_ns}}}waypoint"):
                    x = waypoint.get("x")
                    y = waypoint.get("y")
                    waypoints.append(f"{x},{y}")

                # Add RDF triple for edge
                di_uri = f"<http://example.org/di/{edge_id}>"
                self.triples.append(
                    f"{di_uri} a <http://www.omg.org/spec/BPMN/20100524/DI#BPMNEdge> ."
                )
                self.triples.append(f'{di_uri} <{DI}bpmnElement> "{bpmn_element}" .')
                self.triples.append(
                    f'{di_uri} <{DI}waypoint> "{"|".join(waypoints)}" .'
                )


def main():
    parser = argparse.ArgumentParser(
        description="Convert BPMN 2.0 XML files to RDF Turtle format"
    )
    parser.add_argument("input_file", help="Input BPMN XML file")
    parser.add_argument("-o", "--output", help="Output Turtle file (default: stdout)")

    args = parser.parse_args()

    try:
        converter = BPMNToRDFConverter()
        rdf_output = converter.parse_bpmn(args.input_file)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
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


if __name__ == "__main__":
    main()
