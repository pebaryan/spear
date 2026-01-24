# Multi-Instance Handler for SPEAR Engine
# Handles multi-instance (loop) activity execution

import uuid
import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from rdflib import URIRef, Literal, RDF, Graph

from src.api.storage.base import BPMN, INST

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MultiInstanceHandler:
    """
    Handles multi-instance (loop) activity execution in BPMN processes.

    Supports:
    - Parallel multi-instance: All instances execute concurrently
    - Sequential multi-instance: Instances execute one at a time
    - Loop cardinality: Fixed number of iterations
    - Data input/output: Collection-based iteration
    """

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
    ):
        """
        Initialize the multi-instance handler.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
        """
        self._definitions = definitions_graph
        self._instances = instances_graph

    def get_multi_instance_info(self, node_uri: URIRef) -> Dict[str, Any]:
        """
        Check if a node has multi-instance characteristics.

        Args:
            node_uri: URI of the node to check

        Returns:
            Dictionary with multi-instance configuration
        """
        result = {
            "is_multi_instance": False,
            "is_parallel": False,
            "is_sequential": False,
            "loop_cardinality": None,
            "data_input": None,
            "data_output": None,
            "completion_condition": None,
        }

        for _, _, loop_char_uri in self._definitions.triples(
            (node_uri, BPMN.loopCharacteristics, None)
        ):
            result["is_multi_instance"] = True

            # Check type (parallel or sequential)
            for _, _, type_uri in self._definitions.triples(
                (loop_char_uri, RDF.type, None)
            ):
                type_str = str(type_uri)
                if "Parallel" in type_str:
                    result["is_parallel"] = True
                elif "Sequential" in type_str:
                    result["is_sequential"] = True

            # Get loop cardinality
            for _, _, cardinality in self._definitions.triples(
                (loop_char_uri, BPMN.loopCardinality, None)
            ):
                result["loop_cardinality"] = str(cardinality)

            # Alternative cardinality property
            for _, _, cardinality in self._definitions.triples(
                (loop_char_uri, BPMN.cardinality, None)
            ):
                result["loop_cardinality"] = str(cardinality)

            # Get data input/output
            for _, _, data_input in self._definitions.triples(
                (loop_char_uri, BPMN.dataInput, None)
            ):
                result["data_input"] = str(data_input)

            for _, _, data_output in self._definitions.triples(
                (loop_char_uri, BPMN.dataOutput, None)
            ):
                result["data_output"] = str(data_output)

            # Get completion condition
            for _, _, condition in self._definitions.triples(
                (loop_char_uri, BPMN.completionCondition, None)
            ):
                result["completion_condition"] = str(condition)

            break

        return result

    def create_multi_instance_tokens(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        mi_info: Dict[str, Any],
    ) -> List[URIRef]:
        """
        Create tokens for multi-instance activity execution.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the incoming token (will be consumed)
            node_uri: URI of the multi-instance node
            instance_id: ID of the instance
            mi_info: Multi-instance configuration

        Returns:
            List of created token URIs
        """
        created_tokens = []

        # Get loop count
        count = self._get_loop_count(mi_info)

        if mi_info["is_parallel"]:
            logger.info(
                f"Creating {count} parallel tokens for multi-instance activity {node_uri}"
            )

            # Create all tokens at once for parallel execution
            for i in range(count):
                token = self._create_loop_token(instance_uri, node_uri, instance_id, i)
                created_tokens.append(token)

            # Consume the original token
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        elif mi_info["is_sequential"]:
            logger.info(
                f"Creating sequential multi-instance token for {node_uri} (0/{count})"
            )

            # Create first token for sequential execution
            token = self._create_loop_token(
                instance_uri, node_uri, instance_id, 0, total=count
            )
            created_tokens.append(token)

            # Consume the original token
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        return created_tokens

    def _get_loop_count(self, mi_info: Dict[str, Any]) -> int:
        """Get the number of loop iterations."""
        if mi_info["loop_cardinality"]:
            try:
                return int(mi_info["loop_cardinality"])
            except ValueError:
                pass
        return 3  # Default

    def _create_loop_token(
        self,
        instance_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        loop_index: int,
        total: Optional[int] = None,
    ) -> URIRef:
        """Create a token for a loop instance."""
        token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]

        self._instances.add((token_uri, RDF.type, INST.Token))
        self._instances.add((token_uri, INST.belongsTo, instance_uri))
        self._instances.add((token_uri, INST.status, Literal("ACTIVE")))
        self._instances.add((token_uri, INST.currentNode, node_uri))
        self._instances.add((token_uri, INST.loopInstance, Literal(str(loop_index))))
        self._instances.add((instance_uri, INST.hasToken, token_uri))

        if total is not None:
            self._instances.add((token_uri, INST.loopTotal, Literal(str(total))))

        return token_uri

    def complete_loop_instance(
        self,
        instance_uri: URIRef,
        completed_token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        mi_info: Dict[str, Any],
    ) -> bool:
        """
        Handle completion of a single loop instance.

        Args:
            instance_uri: URI of the process instance
            completed_token_uri: URI of the completed loop token
            node_uri: URI of the multi-instance node
            instance_id: ID of the instance
            mi_info: Multi-instance configuration

        Returns:
            True if all loop instances are complete and we should advance
        """
        # Get loop instance number
        instance_num = self._get_loop_instance_number(completed_token_uri)
        total_count = self._get_loop_total(completed_token_uri, mi_info)

        if mi_info["is_parallel"]:
            return self._complete_parallel_instance(
                instance_uri,
                completed_token_uri,
                node_uri,
                instance_id,
                instance_num,
                total_count,
            )
        elif mi_info["is_sequential"]:
            return self._complete_sequential_instance(
                instance_uri,
                completed_token_uri,
                node_uri,
                instance_id,
                instance_num,
                total_count,
            )

        return False

    def _get_loop_instance_number(self, token_uri: URIRef) -> int:
        """Get the loop instance number from a token."""
        for o in self._instances.objects(token_uri, INST.loopInstance):
            try:
                return int(str(o))
            except (ValueError, TypeError):
                pass
        return 0

    def _get_loop_total(self, token_uri: URIRef, mi_info: Dict[str, Any]) -> int:
        """Get the total loop count."""
        # Try from token first
        for o in self._instances.objects(token_uri, INST.loopTotal):
            try:
                return int(str(o))
            except (ValueError, TypeError):
                pass

        # Fall back to mi_info
        return self._get_loop_count(mi_info)

    def _complete_parallel_instance(
        self,
        instance_uri: URIRef,
        completed_token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        instance_num: int,
        total_count: int,
    ) -> bool:
        """Handle parallel loop instance completion."""
        # Count consumed tokens at this node
        consumed_count = 0
        for tok in self._instances.objects(instance_uri, INST.hasToken):
            status = self._instances.value(tok, INST.status)
            current = self._instances.value(tok, INST.currentNode)
            if status and str(status) == "CONSUMED" and current == node_uri:
                consumed_count += 1

        # Check if already advanced
        next_nodes = self._get_outgoing_targets(node_uri)
        already_advanced = self._check_already_advanced(instance_uri, next_nodes)

        # Should advance if this is the last token and we haven't advanced yet
        should_advance = not already_advanced and consumed_count >= total_count - 1

        # Mark token as consumed
        self._instances.set((completed_token_uri, INST.status, Literal("CONSUMED")))

        logger.info(
            f"Parallel loop {instance_num} completed. "
            f"{consumed_count}/{total_count} instances done, advance={should_advance}"
        )

        if should_advance:
            self.advance_past_activity(instance_uri, node_uri, instance_id)
            return True

        return False

    def _complete_sequential_instance(
        self,
        instance_uri: URIRef,
        completed_token_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        instance_num: int,
        total_count: int,
    ) -> bool:
        """Handle sequential loop instance completion."""
        # Mark token as consumed
        self._instances.set((completed_token_uri, INST.status, Literal("CONSUMED")))

        next_instance = instance_num + 1

        if next_instance < total_count:
            # Create next sequential token
            self._create_loop_token(
                instance_uri, node_uri, instance_id, next_instance, total=total_count
            )

            logger.info(
                f"Sequential loop {instance_num} completed. "
                f"Starting instance {next_instance}/{total_count}"
            )
            return False
        else:
            # All done - advance past activity
            logger.info(
                f"Sequential loop {instance_num} completed. "
                f"All {total_count} instances done"
            )
            self.advance_past_activity(instance_uri, node_uri, instance_id)
            return True

    def _get_outgoing_targets(self, node_uri: URIRef) -> List[URIRef]:
        """Get target nodes from outgoing sequence flows."""
        targets = []

        for _, _, flow_uri in self._definitions.triples(
            (node_uri, BPMN.outgoing, None)
        ):
            for _, _, target in self._definitions.triples(
                (flow_uri, BPMN.targetRef, None)
            ):
                targets.append(target)
                break

        return targets

    def _check_already_advanced(
        self,
        instance_uri: URIRef,
        next_nodes: List[URIRef],
    ) -> bool:
        """Check if we've already advanced past the activity."""
        for next_node in next_nodes:
            for tok in self._instances.objects(instance_uri, INST.hasToken):
                current = self._instances.value(tok, INST.currentNode)
                if current == next_node:
                    return True
        return False

    def advance_past_activity(
        self,
        instance_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
    ) -> Optional[URIRef]:
        """
        Advance past a completed multi-instance activity.

        Args:
            instance_uri: URI of the process instance
            node_uri: URI of the completed activity
            instance_id: ID of the instance

        Returns:
            URI of the created token, or None if no outgoing flows
        """
        next_nodes = self._get_outgoing_targets(node_uri)

        if not next_nodes:
            return None

        # Create token at first next node
        token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]

        self._instances.add((token_uri, RDF.type, INST.Token))
        self._instances.add((token_uri, INST.belongsTo, instance_uri))
        self._instances.add((token_uri, INST.status, Literal("ACTIVE")))
        self._instances.add((token_uri, INST.currentNode, next_nodes[0]))
        self._instances.add((instance_uri, INST.hasToken, token_uri))

        # Also update instance current node (for compatibility)
        self._instances.set((instance_uri, INST.currentNode, next_nodes[0]))

        logger.info(f"Advanced past multi-instance activity to {next_nodes[0]}")

        return token_uri
