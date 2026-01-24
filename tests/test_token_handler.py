# Tests for Token Handler
# Verifies token movement and flow control in process execution

import tempfile
import pytest
from rdflib import URIRef, RDF, Literal

from src.api.storage.base import BaseStorageService, INST, BPMN
from src.api.execution.token_handler import TokenHandler


class TestTokenHandlerBasics:
    """Basic tests for TokenHandler."""

    def _create_test_process(self, base: BaseStorageService):
        """Create a simple process definition with two tasks connected by a flow."""
        process_uri = BPMN["TestProcess"]
        task1_uri = BPMN["Task1"]
        task2_uri = BPMN["Task2"]
        flow_uri = BPMN["Flow1"]

        # Add process
        base.definitions_graph.add((process_uri, RDF.type, BPMN.Process))

        # Add tasks
        base.definitions_graph.add((task1_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task2_uri, RDF.type, BPMN.ServiceTask))

        # Add flow Task1 -> Task2
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, task1_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, task2_uri))
        base.definitions_graph.add((task1_uri, BPMN.outgoing, flow_uri))
        base.definitions_graph.add((task2_uri, BPMN.incoming, flow_uri))

        return process_uri, task1_uri, task2_uri, flow_uri

    def _create_test_instance(
        self, base: BaseStorageService, instance_id: str, process_uri: URIRef
    ):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        base.instances_graph.add((instance_uri, INST.process, process_uri))
        return instance_uri

    def _create_test_token(
        self,
        base: BaseStorageService,
        instance_uri: URIRef,
        node_uri: URIRef,
        token_id: str = "token1",
        status: str = "ACTIVE",
    ):
        """Create a test token."""
        token_uri = INST[token_id]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal(status)))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_move_to_next_node_simple(self):
        """Test moving a token to the next node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            process_uri, task1_uri, task2_uri, _ = self._create_test_process(base)
            instance_uri = self._create_test_instance(base, "test-inst", process_uri)
            token_uri = self._create_test_token(base, instance_uri, task1_uri)

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            # Move token
            next_nodes = handler.move_to_next_node(instance_uri, token_uri, "test-inst")

            # Verify token moved to task2
            assert len(next_nodes) == 1
            assert next_nodes[0] == task2_uri

            # Verify token current node updated
            current = base.instances_graph.value(token_uri, INST.currentNode)
            assert current == task2_uri

    def test_move_to_next_node_no_outgoing(self):
        """Test moving a token when there's no outgoing flow (end of process)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            process_uri, _, task2_uri, _ = self._create_test_process(base)
            instance_uri = self._create_test_instance(base, "test-inst", process_uri)
            token_uri = self._create_test_token(base, instance_uri, task2_uri)

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            # Move token from task2 (no outgoing)
            next_nodes = handler.move_to_next_node(instance_uri, token_uri, "test-inst")

            # No next nodes
            assert len(next_nodes) == 0

            # Token should be consumed
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"

    def test_consume_token(self):
        """Test consuming a token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            process_uri, task1_uri, _, _ = self._create_test_process(base)
            instance_uri = self._create_test_instance(base, "test-inst", process_uri)
            token_uri = self._create_test_token(base, instance_uri, task1_uri)

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            # Consume token
            handler.consume_token(token_uri)

            # Verify status
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"

    def test_get_token_current_node(self):
        """Test getting token's current node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            process_uri, task1_uri, _, _ = self._create_test_process(base)
            instance_uri = self._create_test_instance(base, "test-inst", process_uri)
            token_uri = self._create_test_token(base, instance_uri, task1_uri)

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            current = handler.get_token_current_node(token_uri)
            assert current == task1_uri

    def test_get_token_status(self):
        """Test getting token status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            process_uri, task1_uri, _, _ = self._create_test_process(base)
            instance_uri = self._create_test_instance(base, "test-inst", process_uri)
            token_uri = self._create_test_token(
                base, instance_uri, task1_uri, status="WAITING"
            )

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            status = handler.get_token_status(token_uri)
            assert status == "WAITING"

    def test_set_token_waiting(self):
        """Test setting token to WAITING status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            process_uri, task1_uri, _, _ = self._create_test_process(base)
            instance_uri = self._create_test_instance(base, "test-inst", process_uri)
            token_uri = self._create_test_token(base, instance_uri, task1_uri)

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            handler.set_token_waiting(token_uri)

            status = handler.get_token_status(token_uri)
            assert status == "WAITING"


class TestTokenHandlerInstanceCompletion:
    """Tests for instance completion checking."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_test_token(
        self,
        base: BaseStorageService,
        instance_uri: URIRef,
        token_id: str,
        status: str = "ACTIVE",
    ):
        """Create a test token."""
        token_uri = INST[token_id]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal(status)))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_is_instance_completed_all_consumed(self):
        """Test that instance is completed when all tokens are consumed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = self._create_test_instance(base, "test-inst")
            self._create_test_token(base, instance_uri, "token1", status="CONSUMED")
            self._create_test_token(base, instance_uri, "token2", status="CONSUMED")

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            assert handler.is_instance_completed(instance_uri) is True

    def test_is_instance_completed_some_active(self):
        """Test that instance is not completed when some tokens are active."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = self._create_test_instance(base, "test-inst")
            self._create_test_token(base, instance_uri, "token1", status="CONSUMED")
            self._create_test_token(base, instance_uri, "token2", status="ACTIVE")

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            assert handler.is_instance_completed(instance_uri) is False

    def test_get_active_tokens(self):
        """Test getting all active tokens for an instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = self._create_test_instance(base, "test-inst")
            token1 = self._create_test_token(
                base, instance_uri, "token1", status="ACTIVE"
            )
            token2 = self._create_test_token(
                base, instance_uri, "token2", status="CONSUMED"
            )
            token3 = self._create_test_token(
                base, instance_uri, "token3", status="ACTIVE"
            )

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            active = handler.get_active_tokens(instance_uri)

            assert len(active) == 2
            assert token1 in active
            assert token3 in active
            assert token2 not in active


class TestTokenHandlerGateway:
    """Tests for gateway-related token operations."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_parallel_gateway_process(self, base: BaseStorageService):
        """Create a process with a parallel gateway (3 incoming flows)."""
        gateway_uri = BPMN["ParallelGateway"]
        next_task_uri = BPMN["NextTask"]
        flow1_uri = BPMN["InFlow1"]
        flow2_uri = BPMN["InFlow2"]
        flow3_uri = BPMN["InFlow3"]
        out_flow_uri = BPMN["OutFlow"]

        # Add gateway
        base.definitions_graph.add((gateway_uri, RDF.type, BPMN.ParallelGateway))

        # Add incoming flows
        for flow_uri in [flow1_uri, flow2_uri, flow3_uri]:
            base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
            base.definitions_graph.add((flow_uri, BPMN.targetRef, gateway_uri))
            base.definitions_graph.add((gateway_uri, BPMN.incoming, flow_uri))

        # Add outgoing flow
        base.definitions_graph.add((out_flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((out_flow_uri, BPMN.sourceRef, gateway_uri))
        base.definitions_graph.add((out_flow_uri, BPMN.targetRef, next_task_uri))
        base.definitions_graph.add((gateway_uri, BPMN.outgoing, out_flow_uri))

        return gateway_uri, next_task_uri

    def _create_token_at_gateway(
        self,
        base: BaseStorageService,
        instance_uri: URIRef,
        gateway_uri: URIRef,
        token_id: str,
    ):
        """Create a token waiting at a gateway."""
        token_uri = INST[token_id]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, gateway_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_count_incoming_flows(self):
        """Test counting incoming flows to a gateway."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri, _ = self._create_parallel_gateway_process(base)

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            count = handler.count_incoming_flows(gateway_uri)
            assert count == 3

    def test_count_waiting_tokens(self):
        """Test counting tokens waiting at a gateway."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri, _ = self._create_parallel_gateway_process(base)
            instance_uri = self._create_test_instance(base, "test-inst")

            # Create 2 tokens at the gateway
            self._create_token_at_gateway(base, instance_uri, gateway_uri, "token1")
            self._create_token_at_gateway(base, instance_uri, gateway_uri, "token2")

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            count = handler.count_waiting_tokens(instance_uri, gateway_uri)
            assert count == 2

    def test_merge_parallel_tokens(self):
        """Test merging tokens at a parallel join gateway."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri, next_task_uri = self._create_parallel_gateway_process(base)
            instance_uri = self._create_test_instance(base, "test-inst")

            # Create 3 tokens at the gateway
            token1 = self._create_token_at_gateway(
                base, instance_uri, gateway_uri, "token1"
            )
            token2 = self._create_token_at_gateway(
                base, instance_uri, gateway_uri, "token2"
            )
            token3 = self._create_token_at_gateway(
                base, instance_uri, gateway_uri, "token3"
            )

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            # Merge tokens
            merged_token = handler.merge_parallel_tokens(
                instance_uri, gateway_uri, "test-inst", next_task_uri
            )

            # All original tokens should be consumed
            for token_uri in [token1, token2, token3]:
                status = base.instances_graph.value(token_uri, INST.status)
                assert str(status) == "CONSUMED"

            # New merged token should be at next task
            assert merged_token is not None
            current = base.instances_graph.value(merged_token, INST.currentNode)
            assert current == next_task_uri

    def test_merge_inclusive_tokens(self):
        """Test merging tokens at an inclusive gateway with multiple outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri, next_task_uri = self._create_parallel_gateway_process(base)

            # Add a second outgoing flow
            second_task_uri = BPMN["SecondTask"]
            second_flow_uri = BPMN["OutFlow2"]
            base.definitions_graph.add((second_flow_uri, RDF.type, BPMN.SequenceFlow))
            base.definitions_graph.add((second_flow_uri, BPMN.sourceRef, gateway_uri))
            base.definitions_graph.add(
                (second_flow_uri, BPMN.targetRef, second_task_uri)
            )
            base.definitions_graph.add((gateway_uri, BPMN.outgoing, second_flow_uri))

            instance_uri = self._create_test_instance(base, "test-inst")

            # Create 2 tokens at the gateway
            token1 = self._create_token_at_gateway(
                base, instance_uri, gateway_uri, "token1"
            )
            token2 = self._create_token_at_gateway(
                base, instance_uri, gateway_uri, "token2"
            )

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            # Merge and fork to two outputs
            created_tokens = handler.merge_inclusive_tokens(
                instance_uri,
                gateway_uri,
                "test-inst",
                [next_task_uri, second_task_uri],
            )

            # Original tokens should be consumed
            for token_uri in [token1, token2]:
                status = base.instances_graph.value(token_uri, INST.status)
                assert str(status) == "CONSUMED"

            # Should have created 2 new tokens
            assert len(created_tokens) == 2


class TestTokenHandlerParallelSplit:
    """Tests for parallel split (fork) operations."""

    def _create_split_gateway_process(self, base: BaseStorageService):
        """Create a process with a parallel split gateway (1 input, 3 outputs)."""
        task_uri = BPMN["PreviousTask"]
        gateway_uri = BPMN["SplitGateway"]
        target1_uri = BPMN["Target1"]
        target2_uri = BPMN["Target2"]
        target3_uri = BPMN["Target3"]
        in_flow_uri = BPMN["InFlow"]
        out_flow1_uri = BPMN["OutFlow1"]
        out_flow2_uri = BPMN["OutFlow2"]
        out_flow3_uri = BPMN["OutFlow3"]

        # Add gateway
        base.definitions_graph.add((gateway_uri, RDF.type, BPMN.ParallelGateway))

        # Add incoming flow
        base.definitions_graph.add((in_flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((in_flow_uri, BPMN.sourceRef, task_uri))
        base.definitions_graph.add((in_flow_uri, BPMN.targetRef, gateway_uri))
        base.definitions_graph.add((task_uri, BPMN.outgoing, in_flow_uri))
        base.definitions_graph.add((gateway_uri, BPMN.incoming, in_flow_uri))

        # Add outgoing flows
        for flow_uri, target_uri in [
            (out_flow1_uri, target1_uri),
            (out_flow2_uri, target2_uri),
            (out_flow3_uri, target3_uri),
        ]:
            base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
            base.definitions_graph.add((flow_uri, BPMN.sourceRef, gateway_uri))
            base.definitions_graph.add((flow_uri, BPMN.targetRef, target_uri))
            base.definitions_graph.add((gateway_uri, BPMN.outgoing, flow_uri))

        return task_uri, gateway_uri, [target1_uri, target2_uri, target3_uri]

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_test_token(
        self,
        base: BaseStorageService,
        instance_uri: URIRef,
        node_uri: URIRef,
        token_id: str,
    ):
        """Create a test token."""
        token_uri = INST[token_id]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_move_creates_parallel_tokens(self):
        """Test that moving through a split gateway creates parallel tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            _, gateway_uri, targets = self._create_split_gateway_process(base)
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(
                base, instance_uri, gateway_uri, "token1"
            )

            handler = TokenHandler(base.definitions_graph, base.instances_graph)

            # Move token through gateway
            next_nodes = handler.move_to_next_node(instance_uri, token_uri, "test-inst")

            # Should return all 3 targets
            assert len(next_nodes) == 3
            for target in targets:
                assert target in next_nodes

            # Original token should be at first target
            current = base.instances_graph.value(token_uri, INST.currentNode)
            assert current == targets[0]

            # Should have created 2 additional tokens
            active_tokens = handler.get_active_tokens(instance_uri)
            assert len(active_tokens) == 3
