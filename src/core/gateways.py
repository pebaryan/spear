#!/usr/bin/env python3
"""
Complex Gateway Implementation for SPEAR BPMN Orchestrator

This module provides comprehensive support for BPMN gateway types:
- Exclusive Gateway (XOR) - Single path based on conditions
- Parallel Gateway (AND) - Multiple paths simultaneously  
- Inclusive Gateway - Multiple paths based on conditions
- Event-Based Gateway - Wait for events before proceeding

All gateway types are implemented using RDF and SPARQL for routing decisions.
"""

from rdflib import Graph, Namespace, RDF, Literal, URIRef
import logging

logger = logging.getLogger(__name__)

# BPMN Namespace
BPMN = Namespace("http://dkm.fbk.eu/index.php/BPMN2_Ontology#")
INST = Namespace("http://example.org/instance/")
VAR = Namespace("http://example.org/variables/")


class GatewayContext:
    """
    Context for gateway execution, holding all relevant information
    """
    
    def __init__(
        self,
        gateway_uri: URIRef,
        instance_uri: URIRef,
        gateway_type: str,
        incoming_flows: list,
        outgoing_flows: list,
        instance_variables: dict
    ):
        self.gateway_uri = gateway_uri
        self.instance_uri = instance_uri
        self.gateway_type = gateway_type  # 'exclusive', 'parallel', 'inclusive', 'event_based'
        self.incoming_flows = incoming_flows
        self.outgoing_flows = outgoing_flows
        self.instance_variables = instance_variables
        self.tokens_arrived = []
        self.tokens_to_create = []


class GatewayEvaluator:
    """
    Evaluates gateway conditions and routing decisions
    """
    
    def __init__(self, definitions_graph: Graph, instances_graph: Graph):
        self.def_graph = definitions_graph
        self.inst_graph = instances_graph
    
    def evaluate_exclusive_gateway(self, context: GatewayContext) -> list:
        """
        Evaluate exclusive gateway routing.
        
        Exclusive gateway (XOR) selects exactly one outgoing path based on conditions.
        If no conditions match, the default flow is used.
        
        Args:
            context: GatewayContext with gateway information
            
        Returns:
            List of target URIs to route to (single element list for exclusive)
        """
        targets = []
        default_flow = None
        
        # Find default flow if exists
        default_flow_uri = self.def_graph.value(context.gateway_uri, BPMN.default)
        if not default_flow_uri:
            # Try camunda:default
            default_flow_uri = self.def_graph.value(
                context.gateway_uri, 
                URIRef("http://camunda.org/schema/1.0/bpmn#default")
            )
        
        # Find default flow target
        if default_flow_uri:
            default_target = self.def_graph.value(default_flow_uri, BPMN.targetRef)
        
        # Check each outgoing flow
        for flow_uri in context.outgoing_flows:
            # Skip default flow for now - it's fallback
            if default_flow_uri and flow_uri == default_flow_uri:
                default_flow = (flow_uri, default_target)
                continue
            
            # Evaluate condition
            target_uri = self.def_graph.value(flow_uri, BPMN.targetRef)
            condition_matches = self._evaluate_flow_condition(
                flow_uri,
                context.instance_variables,
                context.instance_uri,
            )
            
            if condition_matches:
                targets.append(target_uri)
                logger.info(f"Exclusive gateway: condition matched on flow {flow_uri}, target: {target_uri}")
                # For exclusive gateway, stop at first match
                break
        
        # No conditions matched - use default flow
        if not targets and default_flow:
            targets.append(default_flow[1])
            logger.info(f"Exclusive gateway: using default flow {default_flow[0]}")
        
        # Fallback: if only one flow and no conditions, use it
        if not targets and len(context.outgoing_flows) == 1:
            target_uri = self.def_graph.value(context.outgoing_flows[0], BPMN.targetRef)
            targets.append(target_uri)
            logger.info(f"Exclusive gateway: single flow without conditions, target: {target_uri}")
        
        return targets
    
    def _evaluate_flow_condition(
        self,
        flow_uri: URIRef,
        variables: dict,
        instance_uri: URIRef = None,
    ) -> bool:
        """
        Evaluate the condition on a single flow.
        
        Supports:
        - Camunda expression: ${var op value}
        - SPARQL ASK query stored in conditionQuery
        
        Args:
            flow_uri: URI of the sequence flow
            variables: Dictionary of instance variables
            
        Returns:
            True if condition passes, False otherwise
        """
        # Try to get condition query first
        condition_query = self.def_graph.value(flow_uri, BPMN.conditionQuery)
        if condition_query:
            return self._evaluate_sparql_condition(
                str(condition_query),
                variables,
                instance_uri,
            )
        
        # Try condition body (Camunda expression)
        condition_body = self.def_graph.value(flow_uri, BPMN.conditionBody)
        if condition_body:
            return self._evaluate_expression_condition(str(condition_body), variables)
        
        # No condition - path is always valid
        return True
    
    def _evaluate_sparql_condition(
        self,
        query_str: str,
        variables: dict,
        instance_uri: URIRef = None,
    ) -> bool:
        """
        Evaluate a SPARQL ASK query against instance variables.
        
        Args:
            query_str: SPARQL ASK query string
            variables: Dictionary of instance variables
            
        Returns:
            True if query returns true, False otherwise
        """
        try:
            # Build a graph containing instance variables for query evaluation.
            instance_graph = Graph()
            for prefix, ns in self.def_graph.namespaces():
                instance_graph.bind(prefix, ns)
            instance_graph.bind("var", VAR)

            instance_subject = instance_uri or URIRef("http://example.org/instance/instance")
            for var_name, var_value in variables.items():
                var_uri = VAR[var_name]
                instance_graph.add((instance_subject, var_uri, Literal(var_value)))

            # Execute ASK query
            result = instance_graph.query(query_str, initNs={"var": VAR})
            if hasattr(result, "askAnswer"):
                return bool(result.askAnswer)
            return bool(result)
        except Exception as e:
            logger.warning(f"SPARQL condition query failed: {e}")
            return False
    
    def _evaluate_expression_condition(self, condition_str: str, variables: dict) -> bool:
        """
        Evaluate a Camunda-style expression condition.
        
        Supports operators: ==, !=, >, <, >=, <=, eq, neq, gt, lt, gte, lte
        
        Args:
            condition_str: Condition string like "${amount > 1000}"
            variables: Dictionary of instance variables
            
        Returns:
            True if condition passes, False otherwise
        """
        import re
        
        # Extract variable, operator, and value from ${var op value} format
        match = re.search(r"\$\{(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|>=|<|!=|=)\s*(.+)\}", condition_str)
        
        if not match:
            # Try without ${}
            match = re.search(r"(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|>=|<|!=|=)\s*(.+)", condition_str)
        
        if not match:
            # No valid condition found
            return True
        
        var_name = match.group(1)
        operator = match.group(2)
        expected_value = match.group(3).strip()
        
        # Strip quotes from expected value
        if (expected_value.startswith("'") and expected_value.endswith("'")) or \
           (expected_value.startswith('"') and expected_value.endswith('"')):
            expected_value = expected_value[1:-1]
        
        # Get actual value from variables
        actual_value = variables.get(var_name)
        
        if actual_value is None:
            logger.warning(f"Variable '{var_name}' not found in instance variables")
            return False
        
        # Convert to comparable types
        try:
            actual_num = float(actual_value)
            expected_num = float(expected_value)
            
            # Numeric comparison
            return self._compare_numeric(actual_num, expected_num, operator)
        except (ValueError, TypeError):
            # String comparison
            return self._compare_string(str(actual_value), str(expected_value), operator)
    
    def _compare_numeric(self, actual: float, expected: float, operator: str) -> bool:
        """Compare two numeric values using the given operator."""
        comparisons = {
            '>': actual > expected,
            '>=': actual >= expected,
            '<': actual < expected,
            '<=': actual <= expected,
            '==': actual == expected,
            'eq': actual == expected,
            'gt': actual > expected,
            'gte': actual >= expected,
            'lt': actual < expected,
            'lte': actual <= expected,
            'neq': actual != expected,
            '!=': actual != expected,
        }
        return comparisons.get(operator, False)
    
    def _compare_string(self, actual: str, expected: str, operator: str) -> bool:
        """Compare two string values using the given operator."""
        comparisons = {
            '==': actual == expected,
            'eq': actual == expected,
            'neq': actual != expected,
            '!=': actual != expected,
        }
        return comparisons.get(operator, False)
    
    def evaluate_parallel_gateway(self, context: GatewayContext) -> list:
        """
        Evaluate parallel gateway routing.
        
        Parallel gateway (AND) activates ALL outgoing paths simultaneously.
        This is used for fork/join patterns.
        
        Args:
            context: GatewayContext with gateway information
            
        Returns:
            List of all target URIs
        """
        targets = []
        
        for flow_uri in context.outgoing_flows:
            target_uri = self.def_graph.value(flow_uri, BPMN.targetRef)
            if target_uri:
                targets.append(target_uri)
                logger.info(f"Parallel gateway: creating path to {target_uri}")
        
        return targets
    
    def evaluate_inclusive_gateway(self, context: GatewayContext) -> list:
        """
        Evaluate inclusive gateway routing.
        
        Inclusive gateway allows multiple paths to be taken based on conditions.
        Unlike exclusive gateway, multiple conditions can match.
        
        Args:
            context: GatewayContext with gateway information
            
        Returns:
            List of target URIs where conditions matched
        """
        targets = []
        
        for flow_uri in context.outgoing_flows:
            target_uri = self.def_graph.value(flow_uri, BPMN.targetRef)
            condition_matches = self._evaluate_flow_condition(
                flow_uri,
                context.instance_variables,
                context.instance_uri,
            )
            
            if condition_matches:
                targets.append(target_uri)
                logger.info(f"Inclusive gateway: condition matched on flow {flow_uri}, target: {target_uri}")
        
        # If no conditions matched and there's a default flow, use it
        if not targets:
            default_flow_uri = self.def_graph.value(context.gateway_uri, BPMN.default)
            if default_flow_uri:
                default_target = self.def_graph.value(default_flow_uri, BPMN.targetRef)
                if default_target:
                    targets.append(default_target)
                    logger.info(f"Inclusive gateway: using default flow {default_flow_uri}")
        
        return targets
    
    def evaluate_event_based_gateway(self, context: GatewayContext) -> list:
        """
        Evaluate event-based gateway routing.
        
        Event-based gateway waits for one of several possible events before proceeding.
        Creates waiting tokens for each message/receive task target.
        
        Args:
            context: GatewayContext with gateway information
            
        Returns:
            List of target URIs (all targets, tokens will wait for events)
        """
        targets = []
        
        for flow_uri in context.outgoing_flows:
            target_uri = self.def_graph.value(flow_uri, BPMN.targetRef)
            if target_uri:
                targets.append(target_uri)
                logger.info(f"Event-based gateway: waiting for event at {target_uri}")
        
        return targets


class GatewayExecutor:
    """
    Executes gateway routing and token management
    """
    
    def __init__(self, definitions_graph: Graph, instances_graph: Graph):
        self.def_graph = definitions_graph
        self.inst_graph = instances_graph
        self.evaluator = GatewayEvaluator(definitions_graph, instances_graph)
    
    def execute_gateway(
        self, 
        gateway_uri: URIRef, 
        instance_uri: URIRef,
        tokens_at_gateway: list = None
    ) -> list:
        """
        Execute a gateway and return next node URIs.
        
        Determines gateway type and delegates to appropriate evaluation method.
        
        Args:
            gateway_uri: URI of the gateway
            instance_uri: URI of the process instance
            tokens_at_gateway: List of token URIs arriving at gateway (for join)
            
        Returns:
            List of next node URIs to route to
        """
        # Determine gateway type
        gateway_type = self._get_gateway_type(gateway_uri)
        logger.info(f"Executing gateway {gateway_uri} of type {gateway_type}")
        
        # Get incoming and outgoing flows
        incoming_flows = list(self.def_graph.objects(gateway_uri, BPMN.incoming))
        outgoing_flows = list(self.def_graph.subjects(BPMN.sourceRef, gateway_uri))
        
        # Get instance variables
        instance_vars = self._get_instance_variables(instance_uri)
        
        # Create gateway context
        context = GatewayContext(
            gateway_uri=gateway_uri,
            instance_uri=instance_uri,
            gateway_type=gateway_type,
            incoming_flows=incoming_flows,
            outgoing_flows=outgoing_flows,
            instance_variables=instance_vars
        )
        
        # Execute based on gateway type
        if gateway_type == 'exclusive':
            targets = self.evaluator.evaluate_exclusive_gateway(context)
        elif gateway_type == 'parallel':
            targets = self.evaluator.evaluate_parallel_gateway(context)
        elif gateway_type == 'inclusive':
            targets = self.evaluator.evaluate_inclusive_gateway(context)
        elif gateway_type == 'event_based':
            targets = self.evaluator.evaluate_event_based_gateway(context)
        else:
            logger.warning(f"Unknown gateway type: {gateway_type}, treating as exclusive")
            targets = self.evaluator.evaluate_exclusive_gateway(context)
        
        return targets
    
    def _get_gateway_type(self, gateway_uri: URIRef) -> str:
        """Determine the type of gateway from its RDF type."""
        node_types = list(self.def_graph.objects(gateway_uri, RDF.type))
        
        for node_type in node_types:
            type_str = str(node_type).lower()
            
            if 'exclusivegateway' in type_str:
                return 'exclusive'
            elif 'parallelgateway' in type_str:
                return 'parallel'
            elif 'inclusivegateway' in type_str:
                return 'inclusive'
            elif 'eventbasedgateway' in type_str:
                return 'event_based'
        
        # Default to exclusive if type not determined
        return 'exclusive'
    
    def _get_instance_variables(self, instance_uri: URIRef) -> dict:
        """Get all variables for an instance as a dictionary."""
        variables = {}
        
        for var_uri in self.inst_graph.objects(instance_uri, INST.hasVariable):
            var_name = self.inst_graph.value(var_uri, VAR.name)
            var_value = self.inst_graph.value(var_uri, VAR.value)
            
            if var_name and var_value:
                variables[str(var_name)] = str(var_value)
        
        return variables
