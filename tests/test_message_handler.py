# Tests for Message Handler
# Verifies message sending, receiving, and routing

import tempfile
import pytest
from rdflib import URIRef, RDF, Literal

from src.api.storage.base import BaseStorageService, INST, BPMN, VAR
from src.api.messaging.message_handler import MessageHandler


class TestMessageHandlerRegistration:
    """Tests for message handler registration."""

    def test_register_handler(self):
        """Test registering a message handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            def my_handler(msg):
                return msg

            result = handler.register_handler(
                "OrderReceived", my_handler, description="Order handler"
            )

            assert result is True
            assert handler.handler_exists("OrderReceived")

    def test_unregister_handler(self):
        """Test unregistering a message handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            def my_handler(msg):
                return msg

            handler.register_handler("ToRemove", my_handler)
            assert handler.handler_exists("ToRemove")

            result = handler.unregister_handler("ToRemove")
            assert result is True
            assert not handler.handler_exists("ToRemove")

    def test_unregister_nonexistent(self):
        """Test unregistering a nonexistent handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.unregister_handler("Nonexistent")
            assert result is False

    def test_get_all_handlers(self):
        """Test getting all registered handlers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            def handler1(msg):
                return msg

            def handler2(msg):
                return msg

            handler.register_handler("Msg1", handler1, description="First")
            handler.register_handler("Msg2", handler2, description="Second")

            all_handlers = handler.get_all_handlers()

            assert len(all_handlers) == 2
            assert "Msg1" in all_handlers
            assert "Msg2" in all_handlers
            assert all_handlers["Msg1"]["description"] == "First"


class TestSendMessage:
    """Tests for message sending functionality."""

    def _create_receive_task_process(self, base: BaseStorageService, message_name: str):
        """Create a process with a receive task waiting for a message."""
        task_uri = BPMN["ReceiveTask1"]
        next_uri = BPMN["NextTask"]
        flow_uri = BPMN["Flow1"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ReceiveTask))
        base.definitions_graph.add((task_uri, BPMN.message, Literal(message_name)))
        base.definitions_graph.add((next_uri, RDF.type, BPMN.ServiceTask))

        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, task_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, next_uri))
        base.definitions_graph.add((task_uri, BPMN.outgoing, flow_uri))

        return task_uri, next_uri

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_waiting_token(
        self,
        base: BaseStorageService,
        instance_uri: URIRef,
        node_uri: URIRef,
        token_id: str = "token1",
    ):
        """Create a token waiting at a receive task."""
        token_uri = INST[token_id]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("WAITING")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_send_message_no_match(self):
        """Test sending a message with no matching receive tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.send_message("NonexistentMessage")

            assert result["status"] == "no_match"
            assert result["matched_count"] == 0

    def test_send_message_matches_waiting_task(self):
        """Test sending a message that matches a waiting receive task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_receive_task_process(base, "OrderConfirmed")
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_waiting_token(base, instance_uri, task_uri)

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.send_message("OrderConfirmed")

            assert result["status"] == "delivered"
            assert result["matched_count"] == 1
            assert len(result["tasks"]) == 1

            # Token should now be ACTIVE
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "ACTIVE"

    def test_send_message_with_variables(self):
        """Test sending a message with variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_receive_task_process(base, "DataMessage")
            instance_uri = self._create_test_instance(base, "test-inst")
            self._create_waiting_token(base, instance_uri, task_uri)

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            variables = {"orderId": "123", "amount": "100.00"}
            result = handler.send_message("DataMessage", variables=variables)

            assert result["status"] == "delivered"
            assert result["matched_count"] == 1

            var_names = []
            for var_uri in base.instances_graph.objects(
                instance_uri, INST.hasVariable
            ):
                name = base.instances_graph.value(var_uri, VAR.name)
                if name:
                    var_names.append(str(name))

            assert "orderId" in var_names
            assert "amount" in var_names

    def test_send_message_to_specific_instance(self):
        """Test sending a message to a specific instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_receive_task_process(base, "TargetedMessage")

            # Create two instances
            instance1_uri = self._create_test_instance(base, "inst-1")
            instance2_uri = self._create_test_instance(base, "inst-2")

            token1_uri = self._create_waiting_token(
                base, instance1_uri, task_uri, "token1"
            )
            token2_uri = self._create_waiting_token(
                base, instance2_uri, task_uri, "token2"
            )

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            # Send to specific instance
            result = handler.send_message("TargetedMessage", instance_id="inst-1")

            assert result["status"] == "delivered"
            assert result["matched_count"] == 1

            # Only token1 should be activated
            status1 = base.instances_graph.value(token1_uri, INST.status)
            status2 = base.instances_graph.value(token2_uri, INST.status)
            assert str(status1) == "ACTIVE"
            assert str(status2) == "WAITING"

    def test_send_message_ignores_active_tokens(self):
        """Test that messages only match WAITING tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_receive_task_process(base, "TestMessage")
            instance_uri = self._create_test_instance(base, "test-inst")

            # Create an ACTIVE token (not waiting)
            token_uri = INST["active_token"]
            base.instances_graph.add((token_uri, RDF.type, INST.Token))
            base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
            base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
            base.instances_graph.add((token_uri, INST.currentNode, task_uri))
            base.instances_graph.add((instance_uri, INST.hasToken, token_uri))

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.send_message("TestMessage")

            assert result["status"] == "no_match"
            assert result["matched_count"] == 0


class TestReceiveTaskExecution:
    """Tests for receive task execution."""

    def _create_receive_task(self, base: BaseStorageService, message_name: str = None):
        """Create a receive task definition."""
        task_uri = BPMN["ReceiveTask"]
        base.definitions_graph.add((task_uri, RDF.type, BPMN.ReceiveTask))
        if message_name:
            base.definitions_graph.add((task_uri, BPMN.message, Literal(message_name)))
        return task_uri

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_active_token(
        self, base: BaseStorageService, instance_uri: URIRef, node_uri: URIRef
    ):
        """Create an active token."""
        token_uri = INST["test_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_execute_receive_task_with_message(self):
        """Test executing a receive task with a message configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_receive_task(base, "WaitForOrder")
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_active_token(base, instance_uri, task_uri)

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            handler.execute_receive_task(instance_uri, token_uri, task_uri, "test-inst")

            # Token should be WAITING
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "WAITING"

    def test_execute_receive_task_no_message(self):
        """Test executing a receive task with no message configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_receive_task(base)  # No message
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_active_token(base, instance_uri, task_uri)

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            handler.execute_receive_task(instance_uri, token_uri, task_uri, "test-inst")

            # Token should be CONSUMED (no message to wait for)
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"


class TestBoundaryEvents:
    """Tests for boundary event handling."""

    def _create_task_with_boundary(self, base: BaseStorageService, message_name: str):
        """Create a task with a message boundary event."""
        task_uri = BPMN["TaskWithBoundary"]
        boundary_uri = BPMN["MessageBoundaryEvent"]
        handler_uri = BPMN["BoundaryHandler"]
        flow_uri = BPMN["BoundaryFlow"]

        # Task
        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.hasBoundaryEvent, boundary_uri))

        # Boundary event
        base.definitions_graph.add((boundary_uri, RDF.type, BPMN.MessageBoundaryEvent))
        base.definitions_graph.add((boundary_uri, BPMN.messageRef, BPMN[message_name]))
        base.definitions_graph.add((boundary_uri, BPMN.interrupting, Literal("true")))

        # Outgoing flow from boundary
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, boundary_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, handler_uri))
        base.definitions_graph.add((boundary_uri, BPMN.outgoing, flow_uri))

        return task_uri, boundary_uri, handler_uri

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_token_at_task(
        self, base: BaseStorageService, instance_uri: URIRef, task_uri: URIRef
    ):
        """Create an active token at a task."""
        token_uri = INST["boundary_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, task_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_get_outgoing_flows(self):
        """Test getting outgoing flows from a node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            _, boundary_uri, handler_uri = self._create_task_with_boundary(
                base, "CancelOrder"
            )

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            targets = handler.get_outgoing_flows(boundary_uri)

            assert len(targets) == 1
            assert targets[0] == handler_uri

    def test_trigger_interrupting_boundary_event(self):
        """Test triggering an interrupting boundary event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, boundary_uri, _ = self._create_task_with_boundary(
                base, "Interrupt"
            )
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_token_at_task(base, instance_uri, task_uri)

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.trigger_boundary_event(
                token_uri,
                instance_uri,
                boundary_uri,
                "test-inst",
                is_interrupting=True,
            )

            assert result is True

            # Token should be at boundary event now
            current = base.instances_graph.value(token_uri, INST.currentNode)
            assert current == boundary_uri

    def test_trigger_noninterrupting_boundary_event(self):
        """Test triggering a non-interrupting boundary event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, boundary_uri, _ = self._create_task_with_boundary(
                base, "NonInterrupt"
            )
            instance_uri = self._create_test_instance(base, "test-inst")
            original_token = self._create_token_at_task(base, instance_uri, task_uri)

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.trigger_boundary_event(
                original_token,
                instance_uri,
                boundary_uri,
                "test-inst",
                is_interrupting=False,
            )

            assert result is True

            # Original token should still be at task
            original_current = base.instances_graph.value(
                original_token, INST.currentNode
            )
            assert original_current == task_uri

            # A new token should have been created
            token_count = 0
            for _ in base.instances_graph.objects(instance_uri, INST.hasToken):
                token_count += 1
            assert token_count == 2

    def test_trigger_boundary_event_no_outgoing(self):
        """Test triggering boundary event with no outgoing flows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["TaskNoOut"]
            boundary_uri = BPMN["BoundaryNoOut"]

            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
            base.definitions_graph.add(
                (boundary_uri, RDF.type, BPMN.MessageBoundaryEvent)
            )
            base.definitions_graph.add((task_uri, BPMN.hasBoundaryEvent, boundary_uri))
            # No outgoing flow

            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_token_at_task(base, instance_uri, task_uri)

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.trigger_boundary_event(
                token_uri,
                instance_uri,
                boundary_uri,
                "test-inst",
                is_interrupting=True,
            )

            assert result is False


class TestMessageEndEvent:
    """Tests for message end event handling."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def test_trigger_message_end_event(self):
        """Test triggering a message from a message end event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = self._create_test_instance(base, "test-inst")

            log_events = []

            def log_callback(inst, event_type, user, message):
                log_events.append(
                    {
                        "instance": inst,
                        "event_type": event_type,
                        "message": message,
                    }
                )

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            handler.trigger_message_end_event(
                instance_uri, "OrderComplete", log_callback=log_callback
            )

            # Should have logged the message thrown event
            assert len(log_events) == 1
            assert log_events[0]["event_type"] == "MESSAGE_THROWN"
            assert "OrderComplete" in log_events[0]["message"]


class TestEdgeCases:
    """Tests for edge cases."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def test_send_message_with_correlation_id(self):
        """Test sending a message with a correlation ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.send_message(
                "CorrelatedMessage",
                correlation_id="order-12345",
            )

            # Should complete without error
            assert result["status"] == "no_match"  # No tasks to match

    def test_multiple_matching_tasks(self):
        """Test message matching multiple waiting tasks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)

            # Create receive task definition
            task_uri = BPMN["MultiReceive"]
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ReceiveTask))
            base.definitions_graph.add(
                (task_uri, BPMN.message, Literal("BroadcastMsg"))
            )

            # Create multiple instances waiting
            for i in range(3):
                instance_uri = self._create_test_instance(base, f"inst-{i}")
                token_uri = INST[f"token-{i}"]
                base.instances_graph.add((token_uri, RDF.type, INST.Token))
                base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
                base.instances_graph.add((token_uri, INST.status, Literal("WAITING")))
                base.instances_graph.add((token_uri, INST.currentNode, task_uri))
                base.instances_graph.add((instance_uri, INST.hasToken, token_uri))

            handler = MessageHandler(base.definitions_graph, base.instances_graph)

            result = handler.send_message("BroadcastMsg")

            assert result["status"] == "delivered"
            assert result["matched_count"] == 3
            assert len(result["tasks"]) == 3
