# Tests for Event Bus Infrastructure
# Verifies the event-driven architecture foundation

import pytest
from rdflib import URIRef

from src.api.events import (
    ExecutionEventBus,
    ExecutionEvent,
    TokenMovedEvent,
    TokenCreatedEvent,
    TaskCreatedEvent,
    ErrorThrownEvent,
    get_event_bus,
    reset_event_bus,
)


class TestExecutionEventBus:
    """Tests for the ExecutionEventBus class."""

    def test_subscribe_and_publish(self):
        """Test basic subscribe and publish functionality."""
        bus = ExecutionEventBus()
        received_events = []

        def handler(event: TokenMovedEvent):
            received_events.append(event)

        bus.subscribe(TokenMovedEvent, handler)

        event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0] == event

    def test_multiple_subscribers(self):
        """Test that multiple subscribers all receive the event."""
        bus = ExecutionEventBus()
        results = {"handler1": 0, "handler2": 0}

        def handler1(event):
            results["handler1"] += 1

        def handler2(event):
            results["handler2"] += 1

        bus.subscribe(TokenMovedEvent, handler1)
        bus.subscribe(TokenMovedEvent, handler2)

        event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(event)

        assert results["handler1"] == 1
        assert results["handler2"] == 1

    def test_different_event_types(self):
        """Test that handlers only receive their subscribed event types."""
        bus = ExecutionEventBus()
        token_events = []
        task_events = []

        def token_handler(event):
            token_events.append(event)

        def task_handler(event):
            task_events.append(event)

        bus.subscribe(TokenMovedEvent, token_handler)
        bus.subscribe(TaskCreatedEvent, task_handler)

        # Publish a token event
        token_event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(token_event)

        # Publish a task event
        task_event = TaskCreatedEvent(
            instance_uri=URIRef("http://example.org/instance/1"),
            node_uri=URIRef("http://example.org/node/1"),
            token_uri=URIRef("http://example.org/token/1"),
            task_name="Review Document",
        )
        bus.publish(task_event)

        assert len(token_events) == 1
        assert len(task_events) == 1
        assert token_events[0] == token_event
        assert task_events[0] == task_event

    def test_unsubscribe(self):
        """Test unsubscribing a handler."""
        bus = ExecutionEventBus()
        received_events = []

        def handler(event):
            received_events.append(event)

        bus.subscribe(TokenMovedEvent, handler)

        # Publish first event
        event1 = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(event1)

        # Unsubscribe
        result = bus.unsubscribe(TokenMovedEvent, handler)
        assert result is True

        # Publish second event
        event2 = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/2"),
            target_nodes=[URIRef("http://example.org/node/3")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(event2)

        # Should only have received the first event
        assert len(received_events) == 1
        assert received_events[0] == event1

    def test_unsubscribe_not_found(self):
        """Test unsubscribing a handler that was never subscribed."""
        bus = ExecutionEventBus()

        def handler(event):
            pass

        result = bus.unsubscribe(TokenMovedEvent, handler)
        assert result is False

    def test_global_subscriber(self):
        """Test that global subscribers receive all events."""
        bus = ExecutionEventBus()
        all_events = []

        def global_handler(event):
            all_events.append(event)

        bus.subscribe_all(global_handler)

        # Publish different event types
        token_event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(token_event)

        error_event = ErrorThrownEvent(
            instance_uri=URIRef("http://example.org/instance/1"),
            source_node_uri=URIRef("http://example.org/node/1"),
            error_code="ERR001",
            error_message="Something went wrong",
        )
        bus.publish(error_event)

        assert len(all_events) == 2
        assert all_events[0] == token_event
        assert all_events[1] == error_event

    def test_global_subscriber_called_first(self):
        """Test that global subscribers are called before type-specific ones."""
        bus = ExecutionEventBus()
        call_order = []

        def global_handler(event):
            call_order.append("global")

        def type_handler(event):
            call_order.append("type")

        bus.subscribe_all(global_handler)
        bus.subscribe(TokenMovedEvent, type_handler)

        event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(event)

        assert call_order == ["global", "type"]

    def test_has_subscribers(self):
        """Test checking for subscribers."""
        bus = ExecutionEventBus()

        assert bus.has_subscribers(TokenMovedEvent) is False

        def handler(event):
            pass

        bus.subscribe(TokenMovedEvent, handler)
        assert bus.has_subscribers(TokenMovedEvent) is True
        assert bus.has_subscribers(TaskCreatedEvent) is False

    def test_get_subscriber_count(self):
        """Test getting subscriber counts."""
        bus = ExecutionEventBus()

        assert bus.get_subscriber_count() == 0
        assert bus.get_subscriber_count(TokenMovedEvent) == 0

        def handler1(event):
            pass

        def handler2(event):
            pass

        bus.subscribe(TokenMovedEvent, handler1)
        bus.subscribe(TokenMovedEvent, handler2)
        bus.subscribe(TaskCreatedEvent, handler1)

        assert bus.get_subscriber_count(TokenMovedEvent) == 2
        assert bus.get_subscriber_count(TaskCreatedEvent) == 1
        assert bus.get_subscriber_count() == 3

    def test_clear(self):
        """Test clearing all subscribers."""
        bus = ExecutionEventBus()

        def handler(event):
            pass

        bus.subscribe(TokenMovedEvent, handler)
        bus.subscribe_all(handler)

        assert bus.get_subscriber_count() > 0

        bus.clear()

        assert bus.get_subscriber_count() == 0

    def test_get_subscribed_event_types(self):
        """Test getting list of subscribed event types."""
        bus = ExecutionEventBus()

        def handler(event):
            pass

        bus.subscribe(TokenMovedEvent, handler)
        bus.subscribe(TaskCreatedEvent, handler)

        types = bus.get_subscribed_event_types()

        assert TokenMovedEvent in types
        assert TaskCreatedEvent in types
        assert ErrorThrownEvent not in types

    def test_handler_exception_propagates(self):
        """Test that exceptions in handlers propagate to the caller."""
        bus = ExecutionEventBus()

        def bad_handler(event):
            raise ValueError("Handler error")

        bus.subscribe(TokenMovedEvent, bad_handler)

        event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )

        with pytest.raises(ValueError, match="Handler error"):
            bus.publish(event)

    def test_duplicate_subscription_prevented(self):
        """Test that the same handler can't be subscribed twice."""
        bus = ExecutionEventBus()
        call_count = [0]

        def handler(event):
            call_count[0] += 1

        bus.subscribe(TokenMovedEvent, handler)
        bus.subscribe(TokenMovedEvent, handler)  # Duplicate

        event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )
        bus.publish(event)

        # Should only be called once
        assert call_count[0] == 1


class TestEventBusSingleton:
    """Tests for the singleton event bus functions."""

    def test_get_event_bus_returns_same_instance(self):
        """Test that get_event_bus returns the same instance."""
        reset_event_bus()  # Start fresh

        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

    def test_reset_event_bus_creates_new_instance(self):
        """Test that reset_event_bus creates a new instance."""
        bus1 = get_event_bus()
        reset_event_bus()
        bus2 = get_event_bus()

        assert bus1 is not bus2


class TestExecutionEvents:
    """Tests for event dataclasses."""

    def test_token_moved_event_defaults(self):
        """Test TokenMovedEvent default values."""
        event = TokenMovedEvent(
            token_uri=URIRef("http://example.org/token/1"),
            target_nodes=[URIRef("http://example.org/node/2")],
            instance_uri=URIRef("http://example.org/instance/1"),
        )

        assert event.consume_token is True

    def test_task_created_event_defaults(self):
        """Test TaskCreatedEvent default values."""
        event = TaskCreatedEvent(
            instance_uri=URIRef("http://example.org/instance/1"),
            node_uri=URIRef("http://example.org/node/1"),
            token_uri=URIRef("http://example.org/token/1"),
            task_name="Test Task",
        )

        assert event.assignee is None
        assert event.candidate_users == []
        assert event.candidate_groups == []
        assert event.form_data == {}
        assert event.due_date is None
        assert event.priority is None

    def test_error_thrown_event(self):
        """Test ErrorThrownEvent creation."""
        event = ErrorThrownEvent(
            instance_uri=URIRef("http://example.org/instance/1"),
            source_node_uri=URIRef("http://example.org/node/1"),
            error_code="ERR001",
            error_message="Test error",
        )

        assert event.error_code == "ERR001"
        assert event.error_message == "Test error"
        assert event.token_uri is None

    def test_token_created_event(self):
        """Test TokenCreatedEvent creation."""
        event = TokenCreatedEvent(
            instance_uri=URIRef("http://example.org/instance/1"),
            node_uri=URIRef("http://example.org/node/1"),
            parent_token_uri=URIRef("http://example.org/token/parent"),
            loop_index=2,
        )

        assert event.loop_index == 2
        assert event.parent_token_uri == URIRef("http://example.org/token/parent")
