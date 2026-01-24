# Tests for ExecutionEngine
# Tests the main execution orchestration

import pytest
from rdflib import Graph, URIRef, Literal, RDF, Namespace

from src.api.execution.engine import ExecutionEngine
from src.api.storage.base import BPMN, INST


class TestExecutionEngineInit:
    """Tests for ExecutionEngine initialization."""

    def test_init_with_graphs(self):
        """Test initializing engine with graphs."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)
        assert engine._definitions is defs
        assert engine._instances is insts


class TestGetActiveTokens:
    """Tests for get_active_tokens method."""

    def test_get_active_tokens_empty(self):
        """Test getting active tokens when none exist."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        tokens = engine.get_active_tokens(instance_uri)
        assert tokens == []

    def test_get_active_tokens_returns_active_only(self):
        """Test that only ACTIVE tokens are returned."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token1 = INST.token1
        token2 = INST.token2
        token3 = INST.token3

        # Token 1: ACTIVE
        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((token1, INST.status, Literal("ACTIVE")))

        # Token 2: CONSUMED
        insts.add((instance_uri, INST.hasToken, token2))
        insts.add((token2, INST.status, Literal("CONSUMED")))

        # Token 3: ACTIVE
        insts.add((instance_uri, INST.hasToken, token3))
        insts.add((token3, INST.status, Literal("ACTIVE")))

        tokens = engine.get_active_tokens(instance_uri)
        assert len(tokens) == 2
        assert token1 in tokens
        assert token3 in tokens
        assert token2 not in tokens

    def test_get_active_tokens_excludes_waiting(self):
        """Test that WAITING tokens are not returned."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token1 = INST.token1
        token2 = INST.token2

        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((token1, INST.status, Literal("ACTIVE")))

        insts.add((instance_uri, INST.hasToken, token2))
        insts.add((token2, INST.status, Literal("WAITING")))

        tokens = engine.get_active_tokens(instance_uri)
        assert len(tokens) == 1
        assert token1 in tokens


class TestIsInstanceCompleted:
    """Tests for is_instance_completed method."""

    def test_instance_completed_all_consumed(self):
        """Test instance is completed when all tokens consumed."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token1 = INST.token1
        token2 = INST.token2

        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((token1, INST.status, Literal("CONSUMED")))

        insts.add((instance_uri, INST.hasToken, token2))
        insts.add((token2, INST.status, Literal("CONSUMED")))

        assert engine.is_instance_completed(instance_uri) is True

    def test_instance_not_completed_active_token(self):
        """Test instance is not completed with active token."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token1 = INST.token1
        token2 = INST.token2

        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((token1, INST.status, Literal("CONSUMED")))

        insts.add((instance_uri, INST.hasToken, token2))
        insts.add((token2, INST.status, Literal("ACTIVE")))

        assert engine.is_instance_completed(instance_uri) is False

    def test_instance_not_completed_waiting_token(self):
        """Test instance is not completed with waiting token."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token1 = INST.token1

        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((token1, INST.status, Literal("WAITING")))

        assert engine.is_instance_completed(instance_uri) is False


class TestGetNodeTypes:
    """Tests for get_node_types method."""

    def test_get_node_types_single(self):
        """Test getting single node type."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node = BPMN.Task1
        defs.add((node, RDF.type, BPMN.ServiceTask))

        types = engine.get_node_types(node)
        assert len(types) == 1
        assert BPMN.ServiceTask in types

    def test_get_node_types_multiple(self):
        """Test getting multiple node types."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node = BPMN.Task1
        defs.add((node, RDF.type, BPMN.ServiceTask))
        defs.add((node, RDF.type, BPMN.Activity))

        types = engine.get_node_types(node)
        assert len(types) == 2
        assert BPMN.ServiceTask in types
        assert BPMN.Activity in types

    def test_get_node_types_empty(self):
        """Test getting types for node with no types."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node = BPMN.UnknownNode
        types = engine.get_node_types(node)
        assert types == []


class TestCategorizeNode:
    """Tests for categorize_node method."""

    def test_categorize_start_event(self):
        """Test categorizing start event."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.StartEvent]) == "start_event"

    def test_categorize_end_event(self):
        """Test categorizing end event."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.EndEvent]) == "end_event"

    def test_categorize_service_task(self):
        """Test categorizing service task."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.ServiceTask]) == "service_task"

    def test_categorize_user_task(self):
        """Test categorizing user task."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.UserTask]) == "user_task"

    def test_categorize_receive_task(self):
        """Test categorizing receive task."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.ReceiveTask]) == "receive_task"

    def test_categorize_exclusive_gateway(self):
        """Test categorizing exclusive gateway."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.ExclusiveGateway]) == "exclusive_gateway"

    def test_categorize_parallel_gateway(self):
        """Test categorizing parallel gateway."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.ParallelGateway]) == "parallel_gateway"

    def test_categorize_inclusive_gateway(self):
        """Test categorizing inclusive gateway."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.InclusiveGateway]) == "inclusive_gateway"

    def test_categorize_event_based_gateway(self):
        """Test categorizing event-based gateway."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([BPMN.EventBasedGateway]) == "event_based_gateway"

    def test_categorize_cancel_end_event(self):
        """Test categorizing cancel end event."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.CancelEndEvent]) == "cancel_end_event"

    def test_categorize_error_end_event(self):
        """Test categorizing error end event."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.ErrorEndEvent]) == "error_end_event"

    def test_categorize_terminate_end_event(self):
        """Test categorizing terminate end event."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.TerminateEndEvent]) == "terminate_end_event"

    def test_categorize_message_end_event(self):
        """Test categorizing message end event."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.MessageEndEvent]) == "message_end_event"

    def test_categorize_boundary_event(self):
        """Test categorizing boundary event."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.BoundaryEvent]) == "boundary_event"

    def test_categorize_script_task(self):
        """Test categorizing script task."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.ScriptTask]) == "script_task"

    def test_categorize_intermediate_catch_event(self):
        """Test categorizing intermediate catch event."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert (
            engine.categorize_node([NS.IntermediateCatchEvent])
            == "intermediate_catch_event"
        )

    def test_categorize_intermediate_throw_event(self):
        """Test categorizing intermediate throw event."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert (
            engine.categorize_node([NS.IntermediateThrowEvent])
            == "intermediate_throw_event"
        )

    def test_categorize_expanded_subprocess(self):
        """Test categorizing expanded subprocess."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.ExpandedSubProcess]) == "expanded_subprocess"

    def test_categorize_call_activity(self):
        """Test categorizing call activity."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.CallActivity]) == "call_activity"

    def test_categorize_event_subprocess(self):
        """Test categorizing event subprocess."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.EventSubProcess]) == "event_subprocess"

    def test_categorize_unknown_returns_default(self):
        """Test that unknown types return default."""
        engine = ExecutionEngine(Graph(), Graph())
        NS = Namespace("http://example.org/bpmn/")
        assert engine.categorize_node([NS.UnknownType]) == "default"

    def test_categorize_empty_returns_default(self):
        """Test that empty types return default."""
        engine = ExecutionEngine(Graph(), Graph())
        assert engine.categorize_node([]) == "default"


class TestGetOutgoingTargets:
    """Tests for get_outgoing_targets method."""

    def test_get_outgoing_targets_single(self):
        """Test getting single outgoing target."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node = BPMN.Task1
        flow = BPMN.Flow1
        target = BPMN.Task2

        defs.add((node, BPMN.outgoing, flow))
        defs.add((flow, BPMN.targetRef, target))

        targets = engine.get_outgoing_targets(node)
        assert len(targets) == 1
        assert target in targets

    def test_get_outgoing_targets_multiple(self):
        """Test getting multiple outgoing targets."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node = BPMN.Gateway1
        flow1 = BPMN.Flow1
        flow2 = BPMN.Flow2
        target1 = BPMN.Task1
        target2 = BPMN.Task2

        defs.add((node, BPMN.outgoing, flow1))
        defs.add((flow1, BPMN.targetRef, target1))
        defs.add((node, BPMN.outgoing, flow2))
        defs.add((flow2, BPMN.targetRef, target2))

        targets = engine.get_outgoing_targets(node)
        assert len(targets) == 2
        assert target1 in targets
        assert target2 in targets

    def test_get_outgoing_targets_none(self):
        """Test getting outgoing targets when none exist."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node = BPMN.EndEvent1
        targets = engine.get_outgoing_targets(node)
        assert targets == []


class TestMoveTokenToNext:
    """Tests for move_token_to_next method."""

    def test_move_token_single_target(self):
        """Test moving token to single target."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node1 = BPMN.Task1
        node2 = BPMN.Task2
        flow = BPMN.Flow1

        defs.add((node1, BPMN.outgoing, flow))
        defs.add((flow, BPMN.targetRef, node2))

        instance_uri = INST.test_instance
        token_uri = INST.token1
        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, node1))

        next_nodes = engine.move_token_to_next(instance_uri, token_uri, "inst1")

        assert len(next_nodes) == 1
        assert node2 in next_nodes
        assert insts.value(token_uri, INST.currentNode) == node2

    def test_move_token_multiple_targets_creates_tokens(self):
        """Test moving token with multiple targets creates new tokens."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        gateway = BPMN.Gateway1
        target1 = BPMN.Task1
        target2 = BPMN.Task2
        flow1 = BPMN.Flow1
        flow2 = BPMN.Flow2

        defs.add((gateway, BPMN.outgoing, flow1))
        defs.add((flow1, BPMN.targetRef, target1))
        defs.add((gateway, BPMN.outgoing, flow2))
        defs.add((flow2, BPMN.targetRef, target2))

        instance_uri = INST.test_instance
        token_uri = INST.token1
        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, gateway))

        next_nodes = engine.move_token_to_next(instance_uri, token_uri, "inst1")

        assert len(next_nodes) == 2

        # Original token moved to first target
        token_node = insts.value(token_uri, INST.currentNode)
        assert token_node in next_nodes

        # New token created for second target
        all_tokens = list(insts.objects(instance_uri, INST.hasToken))
        assert len(all_tokens) == 2

    def test_move_token_no_outgoing_consumes_token(self):
        """Test that token is consumed when no outgoing flows."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        end_event = BPMN.EndEvent1
        instance_uri = INST.test_instance
        token_uri = INST.token1

        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, end_event))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        next_nodes = engine.move_token_to_next(instance_uri, token_uri, "inst1")

        assert next_nodes == []
        assert str(insts.value(token_uri, INST.status)) == "CONSUMED"


class TestTokenManagement:
    """Tests for token management methods."""

    def test_create_token(self):
        """Test creating a new token."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        node_uri = BPMN.Task1

        token_uri = engine.create_token(instance_uri, node_uri, "inst1")

        assert token_uri is not None
        assert (token_uri, RDF.type, INST.Token) in insts
        assert (token_uri, INST.belongsTo, instance_uri) in insts
        assert str(insts.value(token_uri, INST.status)) == "ACTIVE"
        assert insts.value(token_uri, INST.currentNode) == node_uri
        assert (instance_uri, INST.hasToken, token_uri) in insts

    def test_create_token_with_loop_instance(self):
        """Test creating a token with loop instance."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        node_uri = BPMN.Task1

        token_uri = engine.create_token(
            instance_uri, node_uri, "inst1", loop_instance=3
        )

        assert str(insts.value(token_uri, INST.loopInstance)) == "3"

    def test_create_token_with_custom_status(self):
        """Test creating a token with custom status."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        node_uri = BPMN.Task1

        token_uri = engine.create_token(
            instance_uri, node_uri, "inst1", status="WAITING"
        )

        assert str(insts.value(token_uri, INST.status)) == "WAITING"

    def test_consume_token(self):
        """Test consuming a token."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        token_uri = INST.token1
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        engine.consume_token(token_uri)

        assert str(insts.value(token_uri, INST.status)) == "CONSUMED"

    def test_set_token_waiting(self):
        """Test setting token to waiting."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        token_uri = INST.token1
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        engine.set_token_waiting(token_uri)

        assert str(insts.value(token_uri, INST.status)) == "WAITING"

    def test_set_token_error(self):
        """Test setting token to error."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        token_uri = INST.token1
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        engine.set_token_error(token_uri)

        assert str(insts.value(token_uri, INST.status)) == "ERROR"

    def test_get_token_status(self):
        """Test getting token status."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        token_uri = INST.token1
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        assert engine.get_token_status(token_uri) == "ACTIVE"

    def test_get_token_status_none(self):
        """Test getting token status when not set."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        token_uri = INST.token1
        assert engine.get_token_status(token_uri) is None

    def test_get_token_current_node(self):
        """Test getting token current node."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        token_uri = INST.token1
        node_uri = BPMN.Task1
        insts.add((token_uri, INST.currentNode, node_uri))

        assert engine.get_token_current_node(token_uri) == node_uri

    def test_set_token_current_node(self):
        """Test setting token current node."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        token_uri = INST.token1
        node1 = BPMN.Task1
        node2 = BPMN.Task2
        insts.add((token_uri, INST.currentNode, node1))

        engine.set_token_current_node(token_uri, node2)

        assert insts.value(token_uri, INST.currentNode) == node2


class TestInstanceStatus:
    """Tests for instance status methods."""

    def test_set_instance_status(self):
        """Test setting instance status."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        engine.set_instance_status(instance_uri, "COMPLETED")

        assert str(insts.value(instance_uri, INST.status)) == "COMPLETED"
        assert insts.value(instance_uri, INST.updatedAt) is not None

    def test_get_instance_status(self):
        """Test getting instance status."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        insts.add((instance_uri, INST.status, Literal("RUNNING")))

        assert engine.get_instance_status(instance_uri) == "RUNNING"

    def test_get_instance_status_none(self):
        """Test getting instance status when not set."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        assert engine.get_instance_status(instance_uri) is None


class TestGatewayHandling:
    """Tests for gateway handling methods."""

    def test_count_incoming_flows(self):
        """Test counting incoming flows."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        gateway = BPMN.Gateway1
        flow1 = BPMN.Flow1
        flow2 = BPMN.Flow2

        defs.add((gateway, BPMN.incoming, flow1))
        defs.add((gateway, BPMN.incoming, flow2))

        count = engine.count_incoming_flows(gateway)
        assert count == 2

    def test_count_incoming_flows_zero(self):
        """Test counting incoming flows when none exist."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        start = BPMN.StartEvent1
        count = engine.count_incoming_flows(start)
        assert count == 0

    def test_count_waiting_tokens_at_gateway(self):
        """Test counting waiting tokens at gateway."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        gateway = BPMN.Gateway1
        token1 = INST.token1
        token2 = INST.token2
        token3 = INST.token3

        # Token 1: at gateway, ACTIVE
        insts.add((instance_uri, INST.hasToken, token1))
        insts.add((token1, INST.currentNode, gateway))
        insts.add((token1, INST.status, Literal("ACTIVE")))

        # Token 2: at gateway, WAITING
        insts.add((instance_uri, INST.hasToken, token2))
        insts.add((token2, INST.currentNode, gateway))
        insts.add((token2, INST.status, Literal("WAITING")))

        # Token 3: different node
        insts.add((instance_uri, INST.hasToken, token3))
        insts.add((token3, INST.currentNode, BPMN.Task1))
        insts.add((token3, INST.status, Literal("ACTIVE")))

        count = engine.count_waiting_tokens_at_gateway(instance_uri, gateway)
        assert count == 2

    def test_handle_exclusive_gateway_valid_path(self):
        """Test exclusive gateway with valid path."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token_uri = INST.token1
        gateway = BPMN.Gateway1
        next_node = BPMN.Task1

        insts.add((token_uri, INST.currentNode, gateway))

        def evaluate_callback(inst, node):
            return next_node

        engine.handle_exclusive_gateway(
            instance_uri, token_uri, gateway, "inst1", evaluate_callback
        )

        assert insts.value(token_uri, INST.currentNode) == next_node

    def test_handle_exclusive_gateway_no_valid_path(self):
        """Test exclusive gateway with no valid path."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token_uri = INST.token1
        gateway = BPMN.Gateway1

        insts.add((token_uri, INST.currentNode, gateway))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        log_calls = []

        def evaluate_callback(inst, node):
            return None

        def log_callback(inst, event, user, msg):
            log_calls.append((event, msg))

        engine.handle_exclusive_gateway(
            instance_uri, token_uri, gateway, "inst1", evaluate_callback, log_callback
        )

        assert str(insts.value(token_uri, INST.status)) == "ERROR"
        assert len(log_calls) == 1
        assert log_calls[0][0] == "GATEWAY_ERROR"

    def test_handle_parallel_gateway_fork(self):
        """Test parallel gateway forking."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        gateway = BPMN.Gateway1
        target1 = BPMN.Task1
        target2 = BPMN.Task2
        flow1 = BPMN.Flow1
        flow2 = BPMN.Flow2

        defs.add((gateway, BPMN.outgoing, flow1))
        defs.add((flow1, BPMN.targetRef, target1))
        defs.add((gateway, BPMN.outgoing, flow2))
        defs.add((flow2, BPMN.targetRef, target2))

        instance_uri = INST.test_instance
        token_uri = INST.token1

        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, gateway))

        log_calls = []

        def log_callback(inst, event, user, msg):
            log_calls.append((event, msg))

        engine.handle_parallel_gateway(
            instance_uri, token_uri, gateway, "inst1", log_callback
        )

        # Should have 2 tokens now
        all_tokens = list(insts.objects(instance_uri, INST.hasToken))
        assert len(all_tokens) == 2

        # Verify log callback was called
        assert len(log_calls) == 1
        assert log_calls[0][0] == "PARALLEL_GATEWAY_FORK"

    def test_handle_parallel_gateway_single_path(self):
        """Test parallel gateway with single path."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        gateway = BPMN.Gateway1
        target = BPMN.Task1
        flow = BPMN.Flow1

        defs.add((gateway, BPMN.outgoing, flow))
        defs.add((flow, BPMN.targetRef, target))

        instance_uri = INST.test_instance
        token_uri = INST.token1

        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, gateway))

        engine.handle_parallel_gateway(instance_uri, token_uri, gateway, "inst1")

        # Token should be moved
        assert insts.value(token_uri, INST.currentNode) == target

        # No new tokens created
        all_tokens = list(insts.objects(instance_uri, INST.hasToken))
        assert len(all_tokens) == 1


class TestExecuteToken:
    """Tests for execute_token method."""

    def test_execute_token_no_current_node(self):
        """Test executing token with no current node sets error."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token_uri = INST.token1
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        log_calls = []

        def log_callback(inst, event, user, msg):
            log_calls.append((event, msg))

        engine.execute_token(
            instance_uri, token_uri, "inst1", log_callback=log_callback
        )

        assert str(insts.value(token_uri, INST.status)) == "ERROR"
        assert len(log_calls) == 1
        assert log_calls[0][0] == "TOKEN_ERROR"

    def test_execute_token_skips_consumed(self):
        """Test that consumed tokens are skipped."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token_uri = INST.token1
        node = BPMN.Task1

        insts.add((token_uri, INST.currentNode, node))
        insts.add((token_uri, INST.status, Literal("CONSUMED")))

        handler_calls = []

        handlers = {
            "service_task": lambda *args: handler_calls.append("service_task"),
        }

        defs.add((node, RDF.type, BPMN.ServiceTask))

        engine.execute_token(instance_uri, token_uri, "inst1", handlers=handlers)

        # Handler should not be called
        assert len(handler_calls) == 0

    def test_execute_token_skips_waiting(self):
        """Test that waiting tokens are skipped."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token_uri = INST.token1
        node = BPMN.Task1

        insts.add((token_uri, INST.currentNode, node))
        insts.add((token_uri, INST.status, Literal("WAITING")))

        handler_calls = []

        handlers = {
            "service_task": lambda *args: handler_calls.append("service_task"),
        }

        defs.add((node, RDF.type, BPMN.ServiceTask))

        engine.execute_token(instance_uri, token_uri, "inst1", handlers=handlers)

        # Handler should not be called
        assert len(handler_calls) == 0

    def test_execute_token_dispatches_to_handler(self):
        """Test that token execution dispatches to correct handler."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        instance_uri = INST.test_instance
        token_uri = INST.token1
        node = BPMN.Task1

        insts.add((token_uri, INST.currentNode, node))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        defs.add((node, RDF.type, BPMN.ServiceTask))

        handler_calls = []

        def service_handler(inst_uri, tok_uri, node_uri, inst_id, merged):
            handler_calls.append(("service_task", inst_uri, tok_uri, node_uri))

        handlers = {
            "service_task": service_handler,
        }

        engine.execute_token(instance_uri, token_uri, "inst1", handlers=handlers)

        assert len(handler_calls) == 1
        assert handler_calls[0][0] == "service_task"
        assert handler_calls[0][1] == instance_uri
        assert handler_calls[0][2] == token_uri
        assert handler_calls[0][3] == node

    def test_execute_token_default_moves_to_next(self):
        """Test that default handler moves token to next node."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        node1 = BPMN.Node1
        node2 = BPMN.Node2
        flow = BPMN.Flow1

        defs.add((node1, RDF.type, BPMN.Activity))  # Generic activity
        defs.add((node1, BPMN.outgoing, flow))
        defs.add((flow, BPMN.targetRef, node2))

        instance_uri = INST.test_instance
        token_uri = INST.token1

        insts.add((token_uri, INST.currentNode, node1))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        # No handlers provided - should use default
        engine.execute_token(instance_uri, token_uri, "inst1")

        assert insts.value(token_uri, INST.currentNode) == node2


class TestExecuteInstance:
    """Tests for execute_instance method."""

    def test_execute_instance_simple_flow(self):
        """Test executing simple instance flow."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        # Simple flow: Start -> Task -> End
        start = BPMN.Start1
        task = BPMN.Task1
        end = BPMN.End1
        flow1 = BPMN.Flow1
        flow2 = BPMN.Flow2

        defs.add((start, RDF.type, BPMN.StartEvent))
        defs.add((start, BPMN.outgoing, flow1))
        defs.add((flow1, BPMN.targetRef, task))
        defs.add((task, RDF.type, BPMN.ServiceTask))
        defs.add((task, BPMN.outgoing, flow2))
        defs.add((flow2, BPMN.targetRef, end))
        defs.add((end, RDF.type, BPMN.EndEvent))

        instance_uri = INST.test_instance
        token_uri = INST.token1

        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, RDF.type, INST.Token))
        insts.add((token_uri, INST.belongsTo, instance_uri))
        insts.add((token_uri, INST.currentNode, start))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        execution_count = [0]

        def node_executor(inst_uri, tok_uri, inst_id, merged):
            # Move token to next in each iteration
            engine.move_token_to_next(inst_uri, tok_uri, inst_id)
            execution_count[0] += 1

        engine.execute_instance(instance_uri, "inst1", node_executor=node_executor)

        # Should have executed 3 times (start -> task -> end -> consumed)
        assert execution_count[0] == 3
        assert str(insts.value(instance_uri, INST.status)) == "COMPLETED"

    def test_execute_instance_calls_save_callback(self):
        """Test that save callback is called."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        # Simple flow
        start = BPMN.Start1
        end = BPMN.End1
        flow = BPMN.Flow1

        defs.add((start, RDF.type, BPMN.StartEvent))
        defs.add((start, BPMN.outgoing, flow))
        defs.add((flow, BPMN.targetRef, end))
        defs.add((end, RDF.type, BPMN.EndEvent))

        instance_uri = INST.test_instance
        token_uri = INST.token1

        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, start))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        save_calls = [0]

        def node_executor(inst_uri, tok_uri, inst_id, merged):
            engine.move_token_to_next(inst_uri, tok_uri, inst_id)

        def save_callback():
            save_calls[0] += 1

        engine.execute_instance(
            instance_uri,
            "inst1",
            node_executor=node_executor,
            save_callback=save_callback,
        )

        # Save should be called multiple times
        assert save_calls[0] >= 2

    def test_execute_instance_calls_log_callback_on_complete(self):
        """Test that log callback is called when instance completes."""
        defs = Graph()
        insts = Graph()
        engine = ExecutionEngine(defs, insts)

        # Simple flow
        start = BPMN.Start1
        end = BPMN.End1
        flow = BPMN.Flow1

        defs.add((start, RDF.type, BPMN.StartEvent))
        defs.add((start, BPMN.outgoing, flow))
        defs.add((flow, BPMN.targetRef, end))
        defs.add((end, RDF.type, BPMN.EndEvent))

        instance_uri = INST.test_instance
        token_uri = INST.token1

        insts.add((instance_uri, INST.hasToken, token_uri))
        insts.add((token_uri, INST.currentNode, start))
        insts.add((token_uri, INST.status, Literal("ACTIVE")))

        log_calls = []

        def node_executor(inst_uri, tok_uri, inst_id, merged):
            engine.move_token_to_next(inst_uri, tok_uri, inst_id)

        def log_callback(inst_uri, event, user, msg):
            log_calls.append((event, user))

        engine.execute_instance(
            instance_uri,
            "inst1",
            node_executor=node_executor,
            log_callback=log_callback,
        )

        # Should have logged COMPLETED
        assert any(call[0] == "COMPLETED" for call in log_calls)
