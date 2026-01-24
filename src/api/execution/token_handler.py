# Token Handler for SPEAR Engine
# Manages token movement and flow control in process execution

import uuid
import logging
from typing import List, Optional, TYPE_CHECKING

from rdflib import URIRef, Literal, RDF, Graph

from src.api.storage.base import BPMN, INST

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TokenHandler:
    """
    Handles token movement and flow control in BPMN process execution.

    Responsibilities:
    - Moving tokens along sequence flows
    - Creating tokens for parallel branches
    - Consuming tokens at end events
    - Merging tokens at join gateways
    - Checking instance completion
    """

    def __init__(
        self,
        definitions_graph: Graph,
        instances_graph: Graph,
    ):
        """
        Initialize the token handler.

        Args:
            definitions_graph: Graph containing process definitions
            instances_graph: Graph containing process instances
        """
        self._definitions = definitions_graph
        self._instances = instances_graph

    def move_to_next_node(
        self,
        instance_uri: URIRef,
        token_uri: URIRef,
        instance_id: str,
    ) -> List[URIRef]:
        """
        Move token to the next node(s) via sequence flows.

        Args:
            instance_uri: URI of the process instance
            token_uri: URI of the token to move
            instance_id: ID of the instance (for creating new tokens)

        Returns:
            List of target node URIs the token(s) moved to
        """
        current_node = self._instances.value(token_uri, INST.currentNode)
        if not current_node:
            return []

        # Find outgoing sequence flows and their targets
        next_nodes = self._get_outgoing_targets(current_node)

        if next_nodes:
            # Move token to first target
            self._instances.set((token_uri, INST.currentNode, next_nodes[0]))

            # If there are additional targets, create new tokens (for parallel splits)
            for additional_target in next_nodes[1:]:
                self._create_token(instance_uri, additional_target, instance_id)
        else:
            # No outgoing flows - consume token
            self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        return next_nodes

    def _get_outgoing_targets(self, node_uri: URIRef) -> List[URIRef]:
        """Get all target nodes from outgoing sequence flows."""
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

    def _create_token(
        self,
        instance_uri: URIRef,
        node_uri: URIRef,
        instance_id: str,
        status: str = "ACTIVE",
        loop_instance: Optional[int] = None,
    ) -> URIRef:
        """Create a new token at a node."""
        token_uri = INST[f"token_{instance_id}_{str(uuid.uuid4())[:8]}"]

        self._instances.add((token_uri, RDF.type, INST.Token))
        self._instances.add((token_uri, INST.belongsTo, instance_uri))
        self._instances.add((token_uri, INST.status, Literal(status)))
        self._instances.add((token_uri, INST.currentNode, node_uri))
        self._instances.add((instance_uri, INST.hasToken, token_uri))

        if loop_instance is not None:
            self._instances.add(
                (token_uri, INST.loopInstance, Literal(str(loop_instance)))
            )

        return token_uri

    def consume_token(self, token_uri: URIRef) -> None:
        """Mark a token as consumed."""
        self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

    def is_instance_completed(self, instance_uri: URIRef) -> bool:
        """Check if all tokens in an instance are consumed."""
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            status = self._instances.value(token_uri, INST.status)
            if not status or str(status) != "CONSUMED":
                return False
        return True

    def count_incoming_flows(self, gateway_uri: URIRef) -> int:
        """Count the number of incoming sequence flows to a gateway."""
        count = 0
        for _ in self._definitions.triples((gateway_uri, BPMN.incoming, None)):
            count += 1
        return count

    def count_waiting_tokens(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
    ) -> int:
        """Count tokens waiting at a gateway."""
        count = 0

        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            current_node = self._instances.value(token_uri, INST.currentNode)
            if current_node == gateway_uri:
                count += 1

        return count

    def merge_parallel_tokens(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
        instance_id: str,
        next_node: URIRef,
    ) -> URIRef:
        """
        Consume all tokens at a parallel join gateway and create one merged token.

        Args:
            instance_uri: URI of the process instance
            gateway_uri: URI of the gateway
            instance_id: ID of the instance
            next_node: Target node for the merged token

        Returns:
            URI of the newly created merged token
        """
        # Consume all tokens at the gateway
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            current_node = self._instances.value(token_uri, INST.currentNode)
            if current_node == gateway_uri:
                self._instances.set((token_uri, INST.status, Literal("CONSUMED")))

        # Create merged token
        return self._create_token(instance_uri, next_node, instance_id)

    def merge_inclusive_tokens(
        self,
        instance_uri: URIRef,
        gateway_uri: URIRef,
        instance_id: str,
        next_nodes: List[URIRef],
    ) -> List[URIRef]:
        """
        Consume all tokens at an inclusive join gateway and create token(s) for next nodes.

        Args:
            instance_uri: URI of the process instance
            gateway_uri: URI of the gateway
            instance_id: ID of the instance
            next_nodes: Target nodes for the forked tokens

        Returns:
            List of URIs for the newly created tokens
        """
        # Consume all tokens at the gateway
        tokens_consumed = 0
        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            current_node = self._instances.value(token_uri, INST.currentNode)
            if current_node == gateway_uri:
                self._instances.set((token_uri, INST.status, Literal("CONSUMED")))
                tokens_consumed += 1

        # Create tokens for next nodes
        created_tokens = []
        for next_node in next_nodes:
            token = self._create_token(instance_uri, next_node, instance_id)
            created_tokens.append(token)

        logger.debug(
            f"Inclusive gateway {gateway_uri} merged {tokens_consumed} tokens, "
            f"created {len(created_tokens)} new tokens"
        )

        return created_tokens

    def get_token_current_node(self, token_uri: URIRef) -> Optional[URIRef]:
        """Get the current node for a token."""
        return self._instances.value(token_uri, INST.currentNode)

    def get_token_status(self, token_uri: URIRef) -> Optional[str]:
        """Get the status of a token."""
        status = self._instances.value(token_uri, INST.status)
        return str(status) if status else None

    def get_active_tokens(self, instance_uri: URIRef) -> List[URIRef]:
        """Get all active tokens for an instance."""
        active_tokens = []

        for token_uri in self._instances.objects(instance_uri, INST.hasToken):
            status = self._instances.value(token_uri, INST.status)
            if status and str(status) == "ACTIVE":
                active_tokens.append(token_uri)

        return active_tokens

    def set_token_waiting(self, token_uri: URIRef) -> None:
        """Set a token to WAITING status (for user tasks, receive tasks, etc.)."""
        self._instances.set((token_uri, INST.status, Literal("WAITING")))
