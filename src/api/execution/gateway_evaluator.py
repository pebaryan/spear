# Gateway Evaluator for SPEAR Engine
# Evaluates conditions on gateway outgoing flows

import re
import logging
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING

from rdflib import URIRef, Graph

from src.api.storage.base import BPMN, INST, VAR

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class GatewayEvaluator:
    """
    Evaluates conditions on gateway outgoing flows.

    Supports:
    - Exclusive gateways (XOR) - one outgoing path
    - Inclusive gateways (OR) - one or more outgoing paths
    - Default flows when no conditions match

    Condition expressions can be in these formats:
    - ${variable op value} - JUEL-style expressions
    - variable op value - simple expressions

    Supported operators:
    - == or eq: equals
    - != or neq: not equals
    - > or gt: greater than
    - >= or gte: greater than or equal
    - < or lt: less than
    - <= or lte: less than or equal

    BUG FIX: Removed duplicate unreachable code that existed after
    return statement in the original implementation.
    """

    # Regex pattern for condition expressions
    CONDITION_PATTERN_JUEL = re.compile(
        r"\$\{(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|<|=)\s*(.+)\}"
    )
    CONDITION_PATTERN_SIMPLE = re.compile(
        r"(\w+)\s*(>=|<=|!=|==|gte|lte|neq|eq|gt|lt|>|<|=)\s*(.+)"
    )

    # Operator mapping to normalize operators
    OPERATOR_MAP = {
        "==": "=",
        "eq": "=",
        "!=": "!=",
        "neq": "!=",
        ">": ">",
        "gt": ">",
        ">=": ">=",
        "gte": ">=",
        "<": "<",
        "lt": "<",
        "<=": "<=",
        "lte": "<=",
    }

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
    ):
        """
        Initialize the gateway evaluator.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
        """
        self._definitions = definitions_graph
        self._instances = instances_graph

    def evaluate_exclusive_gateway(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
    ) -> Optional[URIRef]:
        """
        Evaluate conditions for an exclusive gateway and return the target node.

        For exclusive gateways:
        - Find all outgoing sequence flows
        - Evaluate each flow's condition
        - Return the first target where condition is True
        - If no match, use the default flow
        - If no default flow and single outgoing flow, use it
        - Otherwise return None (dead end)

        Args:
            instance_uri: URI of the process instance
            gateway_uri: URI of the gateway node

        Returns:
            URIRef of the next node, or None if no valid path
        """
        outgoing_flows = self._get_outgoing_flows(gateway_uri)

        if not outgoing_flows:
            logger.warning(f"Gateway {gateway_uri} has no outgoing flows")
            return None

        # Get default flow
        default_flow = self._get_default_flow(gateway_uri)

        # Get instance variables
        instance_vars = self._get_instance_variables(instance_uri)

        # Evaluate each non-default flow
        for flow_uri, target_uri in outgoing_flows:
            if default_flow and flow_uri == default_flow:
                continue

            if self._evaluate_flow_condition(flow_uri, instance_vars):
                logger.info(
                    f"Condition matched on flow {flow_uri}, proceeding to {target_uri}"
                )
                return target_uri

        # No condition matched - try default flow
        if default_flow:
            for flow_uri, target_uri in outgoing_flows:
                if flow_uri == default_flow:
                    logger.info(f"Using default flow {flow_uri}")
                    return target_uri

        # If only one outgoing flow with no conditions, use it
        if len(outgoing_flows) == 1:
            target = outgoing_flows[0][1]
            logger.info(
                f"No conditions on single outgoing flow, proceeding to {target}"
            )
            return target

        logger.warning(f"No valid path found at exclusive gateway {gateway_uri}")
        return None

    def evaluate_inclusive_gateway(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
    ) -> List[URIRef]:
        """
        Evaluate conditions for an inclusive gateway and return all matching targets.

        For inclusive gateways:
        - Find all outgoing sequence flows
        - Evaluate each flow's condition
        - Return ALL targets where condition is True
        - If no match, use the default flow

        Args:
            instance_uri: URI of the process instance
            gateway_uri: URI of the gateway node

        Returns:
            List of URIRefs for target nodes (may be empty)
        """
        outgoing_flows = self._get_outgoing_flows(gateway_uri)

        if not outgoing_flows:
            logger.warning(f"Gateway {gateway_uri} has no outgoing flows")
            return []

        default_flow = self._get_default_flow(gateway_uri)
        instance_vars = self._get_instance_variables(instance_uri)

        matching_targets = []

        # Evaluate each non-default flow
        for flow_uri, target_uri in outgoing_flows:
            if default_flow and flow_uri == default_flow:
                continue

            if self._evaluate_flow_condition(flow_uri, instance_vars):
                matching_targets.append(target_uri)

        # If nothing matched, use default
        if not matching_targets and default_flow:
            for flow_uri, target_uri in outgoing_flows:
                if flow_uri == default_flow:
                    matching_targets.append(target_uri)
                    break

        logger.info(
            f"Inclusive gateway {gateway_uri} matched {len(matching_targets)} flows"
        )
        return matching_targets

    def evaluate_flow_condition(
        self,
        instance_uri: URIRef,
        flow_uri: URIRef,
    ) -> bool:
        """
        Evaluate a single flow's condition.

        Args:
            instance_uri: URI of the process instance
            flow_uri: URI of the sequence flow

        Returns:
            True if condition passes or no condition, False otherwise
        """
        instance_vars = self._get_instance_variables(instance_uri)
        return self._evaluate_flow_condition(flow_uri, instance_vars)

    def _get_outgoing_flows(
        self,
        gateway_uri: URIRef,
    ) -> List[Tuple[URIRef, URIRef]]:
        """Get all outgoing flows from a gateway as (flow_uri, target_uri) tuples."""
        outgoing_flows = []

        for flow_uri in self._definitions.subjects(BPMN.sourceRef, gateway_uri):
            target_ref = self._definitions.value(flow_uri, BPMN.targetRef)
            if target_ref:
                outgoing_flows.append((flow_uri, target_ref))

        return outgoing_flows

    def _get_default_flow(self, gateway_uri: URIRef) -> Optional[URIRef]:
        """Get the default flow for a gateway."""
        default_flow = self._definitions.value(gateway_uri, BPMN.default)

        if not default_flow:
            # Also check camunda:default
            default_flow = self._definitions.value(
                gateway_uri, URIRef("http://camunda.org/schema/1.0/bpmn#default")
            )

        return default_flow

    def _get_instance_variables(self, instance_uri: URIRef) -> Dict[str, str]:
        """Get all variables for an instance as a dictionary."""
        variables = {}

        for var_uri in self._instances.objects(instance_uri, INST.hasVariable):
            var_name = self._instances.value(var_uri, VAR.name)
            var_value = self._instances.value(var_uri, VAR.value)
            if var_name and var_value:
                variables[str(var_name)] = str(var_value)

        return variables

    def _evaluate_flow_condition(
        self,
        flow_uri: URIRef,
        instance_vars: Dict[str, str],
    ) -> bool:
        """
        Evaluate the condition on a flow.

        Args:
            flow_uri: URI of the sequence flow
            instance_vars: Dictionary of instance variables

        Returns:
            True if condition passes or no condition exists
        """
        try:
            condition_body = self._definitions.value(flow_uri, BPMN.conditionBody)

            if not condition_body:
                # No condition means always True for conditional flows,
                # but we shouldn't reach here for flows without conditions
                return True

            condition_str = str(condition_body)

            # Parse the condition
            parsed = self._parse_condition(condition_str)
            if not parsed:
                logger.warning(
                    f"Unsupported condition expression on flow {flow_uri}: {condition_str}"
                )
                return False

            var_name, operator, expected_value = parsed
            actual_value = instance_vars.get(var_name)

            if actual_value is None:
                return False

            return self._compare_values(actual_value, expected_value, operator)

        except Exception as e:
            logger.warning(f"Failed to evaluate condition on flow {flow_uri}: {e}")
            return False

    def _parse_condition(
        self,
        condition_str: str,
    ) -> Optional[Tuple[str, str, str]]:
        """
        Parse a condition expression.

        Args:
            condition_str: The condition expression string

        Returns:
            Tuple of (variable_name, operator, expected_value) or None
        """
        # Try JUEL-style expression first: ${var op value}
        match = self.CONDITION_PATTERN_JUEL.search(condition_str)

        if not match:
            # Try simple expression: var op value
            match = self.CONDITION_PATTERN_SIMPLE.search(condition_str)

        if not match:
            return None

        var_name = match.group(1)
        operator = match.group(2)
        expected_value = match.group(3).strip()

        # Strip quotes from expected value
        if (expected_value.startswith("'") and expected_value.endswith("'")) or (
            expected_value.startswith('"') and expected_value.endswith('"')
        ):
            expected_value = expected_value[1:-1]

        return var_name, operator, expected_value

    def _compare_values(
        self,
        actual: str,
        expected: str,
        operator: str,
    ) -> bool:
        """
        Compare two values using the given operator.

        Args:
            actual: The actual value (from instance variable)
            expected: The expected value (from condition)
            operator: The comparison operator

        Returns:
            Result of the comparison
        """
        # Normalize operator
        op = self.OPERATOR_MAP.get(operator, operator)

        actual_bool = self._to_bool(actual)
        expected_bool = self._to_bool(expected)
        if actual_bool is not None and expected_bool is not None and op in ("=", "!="):
            return actual_bool == expected_bool if op == "=" else actual_bool != expected_bool

        # Try numeric comparison first
        try:
            actual_num = float(actual)
            expected_num = float(expected)

            if op == "=":
                return actual_num == expected_num
            elif op == "!=":
                return actual_num != expected_num
            elif op == ">":
                return actual_num > expected_num
            elif op == ">=":
                return actual_num >= expected_num
            elif op == "<":
                return actual_num < expected_num
            elif op == "<=":
                return actual_num <= expected_num

        except ValueError:
            pass  # Not numeric, fall through to string comparison

        # String comparison
        if op == "=":
            return actual == expected
        elif op == "!=":
            return actual != expected
        elif op in (">", ">=", "<", "<="):
            # For string inequality comparisons, try numeric first, then lexicographic
            try:
                actual_num = float(actual)
                expected_num = float(expected)
                if op == ">":
                    return actual_num > expected_num
                elif op == ">=":
                    return actual_num >= expected_num
                elif op == "<":
                    return actual_num < expected_num
                elif op == "<=":
                    return actual_num <= expected_num
            except ValueError:
                # Lexicographic comparison
                if op == ">":
                    return actual > expected
                elif op == ">=":
                    return actual >= expected
                elif op == "<":
                    return actual < expected
                elif op == "<=":
                    return actual <= expected

        return False

    def _to_bool(self, value: str) -> Optional[bool]:
        """Convert common boolean strings to bool."""
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "false"):
                return lowered == "true"
        return None
