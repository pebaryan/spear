#!/usr/bin/env python3
"""
RDF to BPMN Converter
Converts RDF Turtle format back to BPMN 2.0 XML format

author: Sonnet 4.5

This module provides conversion from RDF process definitions to BPMN 2.0 XML:
- convert(): Converts a process ID to BPMN XML using storage
- convert_graph(): Converts an RDF graph to BPMN XML string
"""

import xml.etree.ElementTree as ET
from typing import Dict, Set, Optional, List, Any
from rdflib import Graph, Namespace, RDF, RDFS, URIRef, Literal
import uuid
import re


# RDF Namespaces (must match bpmn2rdf.py)
BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
PROC = Namespace("http://example.org/process/")
INST = Namespace("http://example.org/instance/")
VAR = Namespace("http://example.org/variables/")
META = Namespace("http://example.org/meta/")

# BPMN XML Namespaces
BPMN_XML_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN_DI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
CAMUNDA_NS = "http://camunda.org/schema/1.0/bpmn"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


class RDFToBPMNConverter:
    """
    Converts RDF process definitions to BPMN 2.0 XML format.

    Supports:
    - Basic elements: StartEvent, EndEvent, ServiceTask, UserTask
    - Gateways: Exclusive, Parallel, Inclusive
    - SequenceFlow with conditions
    - Process metadata and documentation
    """

    def __init__(self):
        self.namespaces = {
            "bpmn": BPMN_XML_NS,
            "camunda": CAMUNDA_NS,
        }

        # Track elements to avoid duplicates
        self._processed_elements: Set[str] = set()
        self._element_map: Dict[str, ET.Element] = {}

    def convert(self, process_id: str, storage, include_diagram: bool = False) -> str:
        """
        Convert a process ID to BPMN XML.

        Args:
            process_id: The process definition ID
            storage: RDFStorageService instance
            include_diagram: Include diagram interchange (layout) information

        Returns:
            BPMN 2.0 XML as string
        """
        graph = storage.get_process_graph(process_id)
        if not graph:
            raise ValueError(f"Process {process_id} not found")

        return self.convert_graph(graph, process_id, include_diagram)

    def convert_graph(
        self, graph: Graph, process_id: str = None, include_diagram: bool = False
    ) -> str:
        """
        Convert an RDF graph to BPMN XML.

        Args:
            graph: rdflib Graph containing process definition
            process_id: Optional process ID for metadata
            include_diagram: Include diagram interchange (layout) information

        Returns:
            BPMN 2.0 XML as string
        """
        # Reset state
        self._processed_elements.clear()
        self._element_map.clear()

        # Create root element
        root = self._create_definitions_element(graph, process_id)

        # Find process element
        process_elem = self._find_or_create_process_element(root, graph, process_id)

        # Extract all elements and organize by type
        elements_by_type = self._categorize_elements(graph)

        # Add elements in correct order (required by BPMN spec)
        self._add_elements_to_process(process_elem, graph, elements_by_type)

        # Add sequence flows last (they reference other elements)
        self._add_sequence_flows(process_elem, graph, elements_by_type)

        # Add diagram interchange (layout) information if requested
        if include_diagram:
            self._add_diagram_interchange(root, graph)

        # Return as string
        return self._serialize_xml(root)

    def _create_definitions_element(
        self, graph: Graph, process_id: str = None
    ) -> ET.Element:
        """Create the root <definitions> element"""
        root = ET.Element("definitions")
        root.set("xmlns", BPMN_XML_NS)
        root.set("xmlns:camunda", CAMUNDA_NS)
        root.set("targetNamespace", "http://bpmn.io/schema/bpmn")

        # Store process_id for later use
        self._process_id = process_id

        return root

    def _find_or_create_process_element(
        self, root: ET.Element, graph: Graph, process_id: str = None
    ) -> ET.Element:
        """Find or create the <process> element"""
        process = ET.SubElement(root, "process")
        process.set("id", f"Process_{process_id or 'unknown'}")
        process.set("isExecutable", "true")

        # Try to get process name from metadata
        if process_id:
            for s, p, o in graph.triples((PROC[process_id], META.name, None)):
                process.set("name", str(o))
                break

        return process

    def _categorize_elements(self, graph: Graph) -> Dict[str, List]:
        """Categorize all elements by their RDF type"""
        elements = {
            "startevent": [],
            "endevent": [],
            "servicetask": [],
            "usertask": [],
            "exclusivegateway": [],
            "parallelgateway": [],
            "inclusivegateway": [],
            "sequenceflow": [],
            "expandedsubprocess": [],
            "eventsubprocess": [],
            "callactivity": [],
            "intermediatecatchevent": [],
            "intermediatethrowevent": [],
            "boundaryevent": [],
            "othertasks": [],
            "otherevents": [],
        }

        for s, p, o in graph.triples((None, RDF.type, None)):
            elem_uri = str(s)

            # Skip if already processed
            if elem_uri in self._processed_elements:
                continue

            elem_type = str(o).lower()

            if "startevent" in elem_type:
                elements["startevent"].append(s)
            elif "endevent" in elem_type:
                elements["endevent"].append(s)
            elif "servicetask" in elem_type:
                elements["servicetask"].append(s)
            elif "usertask" in elem_type:
                elements["usertask"].append(s)
            elif "exclusivegateway" in elem_type:
                elements["exclusivegateway"].append(s)
            elif "parallelgateway" in elem_type:
                elements["parallelgateway"].append(s)
            elif "inclusivegateway" in elem_type:
                elements["inclusivegateway"].append(s)
            elif "sequenceflow" in elem_type:
                elements["sequenceflow"].append(s)
            elif "expandedsubprocess" in elem_type:
                elements["expandedsubprocess"].append(s)
            elif "eventsubprocess" in elem_type:
                elements["eventsubprocess"].append(s)
            elif "callactivity" in elem_type:
                elements["callactivity"].append(s)
            elif "intermediatecatchevent" in elem_type:
                elements["intermediatecatchevent"].append(s)
            elif "intermediatethrowevent" in elem_type:
                elements["intermediatethrowevent"].append(s)
            elif (
                "messageboundaryevent" in elem_type
                or "timerboundaryevent" in elem_type
                or "errorboundaryevent" in elem_type
                or "signalboundaryevent" in elem_type
            ):
                elements["boundaryevent"].append(s)
            elif "task" in elem_type:
                elements["othertasks"].append(s)
            elif "event" in elem_type:
                elements["otherevents"].append(s)

        return elements

    def _add_elements_to_process(
        self, process_elem: ET.Element, graph: Graph, elements_by_type: Dict[str, List]
    ):
        """Add all elements to the process in correct order"""

        # Order matters: StartEvents → Tasks → Gateways → EndEvents

        # Add start events
        for elem in elements_by_type.get("startevent", []):
            self._add_startevent(process_elem, graph, elem)

        # Add service tasks
        for elem in elements_by_type.get("servicetask", []):
            self._add_servicetask(process_elem, graph, elem)

        # Add user tasks
        for elem in elements_by_type.get("usertask", []):
            self._add_usertask(process_elem, graph, elem)

        # Add other tasks
        for elem in elements_by_type.get("othertasks", []):
            self._add_task(process_elem, graph, elem, "task")

        # Add gateways
        for elem in elements_by_type.get("exclusivegateway", []):
            self._add_gateway(process_elem, graph, elem, "exclusiveGateway")

        for elem in elements_by_type.get("parallelgateway", []):
            self._add_gateway(process_elem, graph, elem, "parallelGateway")

        for elem in elements_by_type.get("inclusivegateway", []):
            self._add_gateway(process_elem, graph, elem, "inclusiveGateway")

        # Add intermediate catch events
        for elem in elements_by_type.get("intermediatecatchevent", []):
            self._add_intermediate_catch_event(process_elem, graph, elem)

        # Add intermediate throw events
        for elem in elements_by_type.get("intermediatethrowevent", []):
            self._add_intermediate_throw_event(process_elem, graph, elem)

        # Add boundary events (after parent activity is created)
        for elem in elements_by_type.get("boundaryevent", []):
            self._add_boundary_event(process_elem, graph, elem)

        # Add expanded subprocesses
        for elem in elements_by_type.get("expandedsubprocess", []):
            self._add_expanded_subprocess(process_elem, graph, elem)

        # Add event subprocesses
        for elem in elements_by_type.get("eventsubprocess", []):
            self._add_event_subprocess(process_elem, graph, elem)

        # Add call activities
        for elem in elements_by_type.get("callactivity", []):
            self._add_call_activity(process_elem, graph, elem)

        # Add end events
        for elem in elements_by_type.get("endevent", []):
            self._add_endevent(process_elem, graph, elem)

    def _add_startevent(self, process_elem: ET.Element, graph: Graph, elem_uri):
        """Convert and add a start event"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "startEvent")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add outgoing flows
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_endevent(self, process_elem: ET.Element, graph: Graph, elem_uri):
        """Convert and add an end event"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "endEvent")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add incoming flows
        self._add_incoming(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_servicetask(self, process_elem: ET.Element, graph: Graph, elem_uri):
        """Convert and add a service task"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "serviceTask")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add camunda:topic
        self._add_camunda_topic(elem, graph, elem_uri)

        # Add multi-instance characteristics if present
        self._add_multi_instance_characteristics(elem, graph, elem_uri)

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_usertask(self, process_elem: ET.Element, graph: Graph, elem_uri):
        """Convert and add a user task"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "userTask")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add assignee if exists
        self._add_assignee(elem, graph, elem_uri)

        # Add multi-instance characteristics if present
        self._add_multi_instance_characteristics(elem, graph, elem_uri)

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_task(
        self, process_elem: ET.Element, graph: Graph, elem_uri, tag_name: str
    ):
        """Convert and add a generic task"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, tag_name)
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_gateway(
        self, process_elem: ET.Element, graph: Graph, elem_uri, gateway_type: str
    ):
        """Convert and add a gateway"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, gateway_type)
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_sequence_flows(
        self, process_elem: ET.Element, graph: Graph, elements_by_type: Dict[str, List]
    ):
        """Add sequence flows (must be added last as they reference other elements)"""
        for elem in elements_by_type.get("sequenceflow", []):
            self._add_sequence_flow(process_elem, graph, elem)

    def _add_sequence_flow(self, process_elem: ET.Element, graph: Graph, flow_uri):
        """Convert and add a sequence flow"""
        flow_str = str(flow_uri)
        if flow_str in self._processed_elements:
            return

        flow = ET.SubElement(process_elem, "sequenceFlow")
        flow.set("id", self._get_element_id(flow_uri))

        # Get source and target
        source = None
        target = None

        for s, p, o in graph.triples((flow_uri, BPMN.sourceRef, None)):
            source = o
        for s, p, o in graph.triples((flow_uri, BPMN.targetRef, None)):
            target = o

        # Add sourceRef (use ID, not full URI)
        if source:
            flow.set("sourceRef", self._get_element_id(source))

        # Add targetRef
        if target:
            flow.set("targetRef", self._get_element_id(target))

        # Add condition expression if exists (exclusive/inclusive gateways)
        self._add_condition_expression(flow, graph, flow_uri)

        # Add documentation if exists
        self._add_documentation(flow, graph, flow_uri)

        # Add name if exists
        self._add_name_attribute(flow, graph, flow_uri)

        self._processed_elements.add(flow_str)

    def _add_incoming(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add incoming sequence flows"""
        for s, p, o in graph.triples((elem_uri, BPMN.incoming, None)):
            incoming = ET.SubElement(elem, "incoming")
            incoming.text = self._get_element_id(o)

    def _add_outgoing(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add outgoing sequence flows"""
        for s, p, o in graph.triples((elem_uri, BPMN.outgoing, None)):
            outgoing = ET.SubElement(elem, "outgoing")
            outgoing.text = self._get_element_id(o)

    def _add_name_attribute(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add name attribute from rdfs:label"""
        for s, p, o in graph.triples((elem_uri, RDFS.label, None)):
            elem.set("name", str(o))
            break

    def _add_camunda_topic(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add camunda:topic for service tasks"""
        # Check BPMN.topic first
        for s, p, o in graph.triples((elem_uri, BPMN.topic, None)):
            elem.set(f"{{{CAMUNDA_NS}}}topic", str(o))
            return

        # Also check camunda namespace directly
        camunda_topic_uri = URIRef(CAMUNDA_NS + "#topic")
        for s, p, o in graph.triples((elem_uri, camunda_topic_uri, None)):
            elem.set(f"{{{CAMUNDA_NS}}}topic", str(o))
            return

    def _add_assignee(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add assignee for user tasks"""
        # Check BPMN.assignee first
        for s, p, o in graph.triples((elem_uri, BPMN.assignee, None)):
            elem.set(f"{{{CAMUNDA_NS}}}assignee", str(o))
            return

        # Also check camunda namespace directly
        camunda_assignee_uri = URIRef(CAMUNDA_NS + "#assignee")
        for s, p, o in graph.triples((elem_uri, camunda_assignee_uri, None)):
            elem.set(f"{{{CAMUNDA_NS}}}assignee", str(o))
            return

    def _add_condition_expression(self, flow: ET.Element, graph: Graph, flow_uri):
        """Add condition expression for sequence flows"""
        # Try to get condition body
        condition_body = None
        condition_type = None

        for s, p, o in graph.triples((flow_uri, BPMN.conditionBody, None)):
            condition_body = str(o)
            break

        for s, p, o in graph.triples((flow_uri, BPMN.conditionType, None)):
            condition_type = str(o)
            break

        if condition_body:
            # Create conditionExpression element
            cond_elem = ET.SubElement(flow, "conditionExpression")

            # Set xsi:type
            if condition_type and "camunda:expression" in condition_type:
                cond_elem.set(f"{{{XSI_NS}}}type", "tFormalExpression")
                cond_elem.set(f"{{{CAMUNDA_NS}}}expression", condition_body)
                cond_elem.text = condition_body
            else:
                cond_elem.set(f"{{{XSI_NS}}}type", "tFormalExpression")
                cond_elem.text = condition_body

    def _add_documentation(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add documentation element to any BPMN element

        Extracts documentation from:
        - bpmn:documentation
        - rdfs:comment
        """
        # Try bpmn:documentation first
        doc_text = None
        for s, p, o in graph.triples((elem_uri, BPMN.documentation, None)):
            doc_text = str(o)
            break

        # Fall back to rdfs:comment
        if not doc_text:
            for s, p, o in graph.triples((elem_uri, RDFS.comment, None)):
                doc_text = str(o)
                break

        # Add documentation element if found
        if doc_text:
            doc_elem = ET.SubElement(elem, "documentation")
            doc_elem.text = doc_text

    def _get_element_id(self, uri) -> str:
        """Extract element ID from URI"""
        uri_str = str(uri)

        # If it's already an ID (no http://)
        if not uri_str.startswith("http"):
            return uri_str

        # Extract from URI like http://example.org/bpmn/StartEvent_1
        if "/bpmn/" in uri_str:
            return uri_str.split("/bpmn/")[-1]

        # Extract from URI like http://example.org/process/uuid
        if "/process/" in uri_str:
            return uri_str.split("/")[-1]

        # Generate a safe ID
        return f"Element_{str(uuid.uuid4())[:8]}"

    def _add_intermediate_catch_event(
        self, process_elem: ET.Element, graph: Graph, elem_uri
    ):
        """Convert and add an intermediate catch event (message, timer, etc.)"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "intermediateCatchEvent")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add message event definition if applicable
        self._add_message_event_definition(elem, graph, elem_uri)

        # Add timer event definition if applicable
        self._add_timer_event_definition(elem, graph, elem_uri)

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_intermediate_throw_event(
        self, process_elem: ET.Element, graph: Graph, elem_uri
    ):
        """Convert and add an intermediate throw event (message)"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "intermediateThrowEvent")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add message event definition if applicable
        self._add_message_event_definition(elem, graph, elem_uri)

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_boundary_event(self, process_elem: ET.Element, graph: Graph, elem_uri):
        """Convert and add a boundary event"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "boundaryEvent")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add attachedToRef (the activity this is attached to)
        for s, p, o in graph.triples((elem_uri, BPMN.attachedToRef, None)):
            elem.set("attachedToRef", self._get_element_id(o))
            break

        # Add interrupting attribute
        is_interrupting = True
        for s, p, o in graph.triples((elem_uri, BPMN.interrupting, None)):
            if str(o).lower() == "false":
                is_interrupting = False
            break
        elem.set("cancelActivity", str(is_interrupting).lower())

        # Add message event definition if applicable
        self._add_message_event_definition(elem, graph, elem_uri)

        # Add timer event definition if applicable
        self._add_timer_event_definition(elem, graph, elem_uri)

        # Add error event definition if applicable
        self._add_error_event_definition(elem, graph, elem_uri)

        # Add signal event definition if applicable
        self._add_signal_event_definition(elem, graph, elem_uri)

        # Add outgoing (boundary events have one outgoing flow)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_message_event_definition(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add message event definition if applicable"""
        for s, p, o in graph.triples((elem_uri, BPMN.messageRef, None)):
            msg_def = ET.SubElement(elem, "messageEventDefinition")
            msg_def.set("messageRef", str(o))
            break

    def _add_timer_event_definition(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add timer event definition if applicable"""
        # Check for timer definitions
        has_timer = False
        for s, p, o in graph.triples((elem_uri, None, None)):
            if "timer" in str(p).lower():
                has_timer = True
                break

        if has_timer:
            timer_def = ET.SubElement(elem, "timerEventDefinition")
            # Add timer duration/date if available

    def _add_error_event_definition(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add error event definition if applicable"""
        for s, p, o in graph.triples((elem_uri, BPMN.errorRef, None)):
            error_def = ET.SubElement(elem, "errorEventDefinition")
            error_def.set("errorRef", str(o))
            break

    def _add_signal_event_definition(self, elem: ET.Element, graph: Graph, elem_uri):
        """Add signal event definition if applicable"""
        for s, p, o in graph.triples((elem_uri, BPMN.signalRef, None)):
            signal_def = ET.SubElement(elem, "signalEventDefinition")
            signal_def.set("signalRef", str(o))
            break

    def _add_expanded_subprocess(
        self, process_elem: ET.Element, graph: Graph, elem_uri
    ):
        """Convert and add an expanded (embedded) subprocess"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "subProcess")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add triggeredByEvent attribute (false for expanded subprocess)
        elem.set("triggeredByEvent", "false")

        # Add multi-instance characteristics if present
        self._add_multi_instance_characteristics(elem, graph, elem_uri)

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        # Add child elements (start events, tasks, etc. inside subprocess)
        self._add_subprocess_children(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_event_subprocess(self, process_elem: ET.Element, graph: Graph, elem_uri):
        """Convert and add an event subprocess"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "subProcess")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add triggeredByEvent attribute (true for event subprocess)
        elem.set("triggeredByEvent", "true")

        # Add child elements
        self._add_subprocess_children(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_call_activity(self, process_elem: ET.Element, graph: Graph, elem_uri):
        """Convert and add a call activity (collapsed subprocess)"""
        elem_str = str(elem_uri)
        if elem_str in self._processed_elements:
            return

        elem = ET.SubElement(process_elem, "callActivity")
        elem.set("id", self._get_element_id(elem_uri))

        # Add documentation if exists
        self._add_documentation(elem, graph, elem_uri)

        # Add name if exists
        self._add_name_attribute(elem, graph, elem_uri)

        # Add calledElement (reference to subprocess)
        for s, p, o in graph.triples((elem_uri, BPMN.calledElement, None)):
            elem.set("calledElement", str(o))
            break

        # Add incoming/outgoing
        self._add_incoming(elem, graph, elem_uri)
        self._add_outgoing(elem, graph, elem_uri)

        self._processed_elements.add(elem_str)
        self._element_map[elem_str] = elem

    def _add_multi_instance_characteristics(
        self, elem: ET.Element, graph: Graph, elem_uri
    ):
        """Add multi-instance loop characteristics to an activity"""
        for s, p, o in graph.triples((elem_uri, BPMN.loopCharacteristics, None)):
            mi_uri = s
            is_parallel = False
            is_sequential = False
            cardinality = None
            completion_condition = None

            # Check if parallel or sequential
            for ss, pp, oo in graph.triples((mi_uri, RDF.type, None)):
                if "parallelmultiinstance" in str(oo).lower():
                    is_parallel = True
                elif "sequentialmultiinstance" in str(oo).lower():
                    is_sequential = True

            # Get loop cardinality
            for ss, pp, oo in graph.triples((mi_uri, BPMN.loopCardinality, None)):
                cardinality = str(oo)

            # Get completion condition
            for ss, pp, oo in graph.triples((mi_uri, BPMN.completionCondition, None)):
                completion_condition = str(oo)

            # Create multiInstanceLoopCharacteristics element
            mi_elem = ET.SubElement(elem, "multiInstanceLoopCharacteristics")

            if is_parallel:
                mi_elem.set("isParallel", "true")
            else:
                mi_elem.set("isParallel", "false")

            if is_sequential:
                mi_elem.set("isSequential", "true")
            else:
                mi_elem.set("isSequential", "false")

            # Add cardinality if present
            if cardinality:
                card_elem = ET.SubElement(mi_elem, "loopCardinality")
                card_elem.text = cardinality

            # Add completion condition if present
            if completion_condition:
                comp_elem = ET.SubElement(mi_elem, "completionCondition")
                comp_elem.text = completion_condition

            break

    def _add_subprocess_children(
        self, subprocess_elem: ET.Element, graph: Graph, parent_uri
    ):
        """Add child elements inside a subprocess"""
        for child_uri in graph.subjects(BPMN.hasParent, parent_uri):
            child_str = str(child_uri)

            if child_str in self._processed_elements:
                continue

            # Get child type
            child_type = None
            for s, p, o in graph.triples((child_uri, RDF.type, None)):
                child_type = str(o).lower()
                break

            if not child_type:
                continue

            # Add child based on type
            if "startevent" in child_type:
                self._add_startevent(subprocess_elem, graph, child_uri)
            elif "endevent" in child_type:
                self._add_endevent(subprocess_elem, graph, child_uri)
            elif "servicetask" in child_type:
                self._add_servicetask(subprocess_elem, graph, child_uri)
            elif "usertask" in child_type:
                self._add_usertask(subprocess_elem, graph, child_uri)
            elif "exclusivegateway" in child_type:
                self._add_gateway(subprocess_elem, graph, child_uri, "exclusiveGateway")
            elif "parallelgateway" in child_type:
                self._add_gateway(subprocess_elem, graph, child_uri, "parallelGateway")
            elif "inclusivegateway" in child_type:
                self._add_gateway(subprocess_elem, graph, child_uri, "inclusiveGateway")
            elif "task" in child_type:
                self._add_task(subprocess_elem, graph, child_uri, "task")
            elif "sequenceflow" in child_type:
                # Sequence flows will be added at the end
                pass

    def _add_diagram_interchange(self, root: ET.Element, graph: Graph):
        """Add BPMNDiagram element with diagram interchange (layout) information.

        Reconstructs the DI section from RDF triples that were extracted from
        the original BPMN file.
        """
        # Define DI namespaces
        bpmndi_ns = "http://www.omg.org/spec/BPMN/20100524/DI"
        dc_ns = "http://www.omg.org/spec/DD/20100524/DC"
        di_ns = "http://www.omg.org/spec/DD/20100524/DI"

        # Define RDF namespaces used in the graph
        DI = Namespace("http://example.org/di/")
        DC = Namespace("http://www.omg.org/spec/DD/20100524/DC#")
        BPMNDI = Namespace("http://www.omg.org/spec/BPMN/20100524/DI#")

        # Add DI namespace declarations to root
        root.set("xmlns:bpmndi", bpmndi_ns)
        root.set("xmlns:dc", dc_ns)
        root.set("xmlns:di", di_ns)

        # Create BPMNDiagram element
        diagram = ET.SubElement(root, f"{{{bpmndi_ns}}}BPMNDiagram")

        # Create BPMNPlane (assume all elements belong to one plane for now)
        plane = ET.SubElement(diagram, f"{{{bpmndi_ns}}}BPMNPlane")

        # Get process ID for the plane
        if self._process_id:
            plane.set("bpmnElement", f"Process_{self._process_id}")
        else:
            plane.set("bpmnElement", "Process_unknown")

        # Find all BPMNShape entries in RDF and create shapes
        for shape_uri in graph.subjects(RDF.type, BPMNDI.Shape):
            shape_id = str(shape_uri).split("/")[-1]
            bpmn_element = graph.value(shape_uri, DI.bpmnElement)

            if not bpmn_element:
                continue

            # Create BPMNShape element
            shape_elem = ET.SubElement(plane, f"{{{bpmndi_ns}}}BPMNShape")
            shape_elem.set("id", shape_id)
            shape_elem.set("bpmnElement", str(bpmn_element))

            # Create Bounds element
            bounds = ET.SubElement(shape_elem, f"{{{dc_ns}}}Bounds")
            x = graph.value(shape_uri, DC.x)
            y = graph.value(shape_uri, DC.y)
            width = graph.value(shape_uri, DC.width)
            height = graph.value(shape_uri, DC.height)

            if x:
                bounds.set("x", str(x))
            if y:
                bounds.set("y", str(y))
            if width:
                bounds.set("width", str(width))
            if height:
                bounds.set("height", str(height))

        # Find all BPMNEdge entries in RDF and create edges
        for edge_uri in graph.subjects(RDF.type, BPMNDI.Edge):
            edge_id = str(edge_uri).split("/")[-1]
            bpmn_element = graph.value(edge_uri, DI.bpmnElement)
            waypoints_str = graph.value(edge_uri, DI.waypoint)

            if not bpmn_element:
                continue

            # Create BPMNEdge element
            edge_elem = ET.SubElement(plane, f"{{{bpmndi_ns}}}BPMNEdge")
            edge_elem.set("id", edge_id)
            edge_elem.set("bpmnElement", str(bpmn_element))

            # Create waypoint elements
            if waypoints_str:
                waypoints = str(waypoints_str).split("|")
                for waypoint_str in waypoints:
                    if "," in waypoint_str:
                        x, y = waypoint_str.split(",", 1)
                        waypoint = ET.SubElement(edge_elem, f"{{{di_ns}}}waypoint")
                        waypoint.set("x", x.strip())
                        waypoint.set("y", y.strip())

    def _serialize_xml(self, root: ET.Element) -> str:
        """Serialize XML element to string with proper formatting"""
        # Add XML declaration
        xml_declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'

        # Serialize with indentation and fix namespace prefixes
        xml_str = ET.tostring(root, encoding="unicode")

        # Replace ns0: prefix with camunda: for camunda namespace attributes
        # ElementTree uses ns0, ns1, etc. for additional namespaces
        import re

        # Fix camunda namespace attributes (ns0 -> camunda)
        xml_str = re.sub(r"ns0:", "camunda:", xml_str)

        # Remove namespace declarations we don't need
        xml_str = re.sub(r'xmlns:ns0="[^"]*"', "", xml_str)

        # Simple formatting (BPMN doesn't require pretty-printing)
        return xml_declaration + xml_str


def main():
    """Main function for command-line usage"""
    import argparse
    from src.api.storage import RDFStorageService

    parser = argparse.ArgumentParser(
        description="Convert RDF process definition to BPMN 2.0 XML"
    )
    parser.add_argument("process_id", help="Process definition ID")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    try:
        storage = RDFStorageService()
        converter = RDFToBPMNConverter()
        bpmn_xml = converter.convert(args.process_id, storage)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(bpmn_xml)
            print(f"BPMN XML written to {args.output}")
        else:
            print(bpmn_xml)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import sys

    main()
