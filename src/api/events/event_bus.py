# Event Bus for SPEAR Engine
# Simple synchronous event bus for execution events

import logging
from typing import Callable, Dict, List, Type, TypeVar, Any
from .execution_events import ExecutionEvent

logger = logging.getLogger(__name__)

# Type variable for event types
E = TypeVar("E", bound=ExecutionEvent)

# Type alias for event handlers
EventHandler = Callable[[ExecutionEvent], None]


class ExecutionEventBus:
    """Simple synchronous event bus for execution events.

    This event bus enables loose coupling between node handlers and
    services. Handlers publish events when they need something done
    (like moving a token or creating a task), and services subscribe
    to handle those events.

    The bus is synchronous - events are processed immediately when
    published. This keeps execution deterministic and easy to debug.

    Example usage:

        # Create the event bus
        bus = ExecutionEventBus()

        # Subscribe a handler
        def on_token_moved(event: TokenMovedEvent):
            print(f"Token {event.token_uri} moved to {event.target_nodes}")

        bus.subscribe(TokenMovedEvent, on_token_moved)

        # Publish an event
        bus.publish(TokenMovedEvent(
            token_uri=token_uri,
            target_nodes=[next_node],
            instance_uri=instance_uri
        ))
    """

    def __init__(self):
        """Initialize the event bus with empty subscriber registry."""
        self._subscribers: Dict[Type[ExecutionEvent], List[EventHandler]] = {}
        self._global_subscribers: List[EventHandler] = []

    def subscribe(self, event_type: Type[E], handler: Callable[[E], None]) -> None:
        """Subscribe a handler to a specific event type.

        Args:
            event_type: The type of event to subscribe to
            handler: Callable that will be invoked when the event is published
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(f"Subscribed {handler.__name__} to {event_type.__name__}")

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe a handler to ALL event types.

        Useful for logging, metrics, or debugging purposes.

        Args:
            handler: Callable that will be invoked for every event
        """
        if handler not in self._global_subscribers:
            self._global_subscribers.append(handler)
            logger.debug(f"Subscribed {handler.__name__} to all events")

    def unsubscribe(self, event_type: Type[E], handler: Callable[[E], None]) -> bool:
        """Unsubscribe a handler from a specific event type.

        Args:
            event_type: The type of event to unsubscribe from
            handler: The handler to remove

        Returns:
            True if the handler was found and removed, False otherwise
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
                logger.debug(
                    f"Unsubscribed {handler.__name__} from {event_type.__name__}"
                )
                return True
            except ValueError:
                return False
        return False

    def unsubscribe_all(self, handler: EventHandler) -> bool:
        """Unsubscribe a handler from the global subscribers.

        Args:
            handler: The handler to remove

        Returns:
            True if the handler was found and removed, False otherwise
        """
        try:
            self._global_subscribers.remove(handler)
            logger.debug(f"Unsubscribed {handler.__name__} from all events")
            return True
        except ValueError:
            return False

    def publish(self, event: ExecutionEvent) -> None:
        """Publish an event to all subscribed handlers.

        Events are processed synchronously in the order handlers
        were subscribed. Global subscribers are called first,
        then type-specific subscribers.

        Args:
            event: The event to publish
        """
        event_type = type(event)
        logger.debug(f"Publishing {event_type.__name__}: {event}")

        # Call global subscribers first
        for handler in self._global_subscribers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in global handler {handler.__name__}: {e}")
                raise

        # Call type-specific subscribers
        if event_type in self._subscribers:
            for handler in self._subscribers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(
                        f"Error in handler {handler.__name__} for {event_type.__name__}: {e}"
                    )
                    raise

    def has_subscribers(self, event_type: Type[ExecutionEvent]) -> bool:
        """Check if an event type has any subscribers.

        Args:
            event_type: The type of event to check

        Returns:
            True if there are subscribers for this event type
        """
        return (
            len(self._global_subscribers) > 0
            or event_type in self._subscribers
            and len(self._subscribers[event_type]) > 0
        )

    def get_subscriber_count(self, event_type: Type[ExecutionEvent] = None) -> int:
        """Get the number of subscribers.

        Args:
            event_type: If provided, count subscribers for this type only.
                       If None, count all subscribers across all types.

        Returns:
            Number of subscribers
        """
        if event_type is not None:
            type_count = len(self._subscribers.get(event_type, []))
            return type_count + len(self._global_subscribers)

        total = len(self._global_subscribers)
        for handlers in self._subscribers.values():
            total += len(handlers)
        return total

    def clear(self) -> None:
        """Remove all subscribers.

        Useful for testing or resetting the bus.
        """
        self._subscribers.clear()
        self._global_subscribers.clear()
        logger.debug("Cleared all event subscribers")

    def get_subscribed_event_types(self) -> List[Type[ExecutionEvent]]:
        """Get a list of all event types that have subscribers.

        Returns:
            List of event types with at least one subscriber
        """
        return [
            event_type
            for event_type, handlers in self._subscribers.items()
            if len(handlers) > 0
        ]


# Singleton instance for shared use across the application
_event_bus_instance: ExecutionEventBus = None


def get_event_bus() -> ExecutionEventBus:
    """Get the shared event bus instance.

    Returns:
        The singleton ExecutionEventBus instance
    """
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = ExecutionEventBus()
    return _event_bus_instance


def reset_event_bus() -> None:
    """Reset the shared event bus instance.

    Creates a new event bus instance, useful for testing.
    """
    global _event_bus_instance
    _event_bus_instance = ExecutionEventBus()
