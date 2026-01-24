# Topic Registry for SPEAR Engine
# Manages service task handler registration and execution

import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TopicRegistry:
    """
    Registry for service task handlers.

    Service tasks in BPMN can be assigned a "topic" which maps to a
    registered handler function. When execution reaches the service task,
    the handler is invoked with the instance variables.

    Supports:
    - Function handlers: Python callables
    - HTTP handlers: External service calls
    - Async execution: For long-running tasks
    """

    def __init__(self):
        """Initialize an empty topic registry."""
        self._handlers: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        topic: str,
        handler_function: Callable,
        description: str = "",
        async_execution: bool = False,
        handler_type: str = "function",
        http_config: Optional[Dict] = None,
    ) -> bool:
        """
        Register a handler for a topic.

        Args:
            topic: The topic name to register
            handler_function: The function to call when the topic is executed
            description: Human-readable description of the handler
            async_execution: Whether to execute asynchronously
            handler_type: Type of handler (http, script, function, webhook)
            http_config: HTTP handler configuration (if applicable)

        Returns:
            True if registered successfully
        """
        self._handlers[topic] = {
            "function": handler_function,
            "description": description,
            "async": async_execution,
            "registered_at": datetime.utcnow().isoformat(),
            "handler_type": handler_type,
            "http_config": http_config,
        }

        logger.info(f"Registered handler for topic: {topic}")
        return True

    def unregister(self, topic: str) -> bool:
        """
        Unregister a handler for a topic.

        Args:
            topic: The topic name to unregister

        Returns:
            True if unregistered, False if topic didn't exist
        """
        if topic in self._handlers:
            del self._handlers[topic]
            logger.info(f"Unregistered handler for topic: {topic}")
            return True
        return False

    def update_description(self, topic: str, description: str) -> bool:
        """
        Update the description of a topic handler.

        Args:
            topic: The topic name
            description: New description

        Returns:
            True if updated, False if topic doesn't exist
        """
        if topic not in self._handlers:
            return False

        self._handlers[topic]["description"] = description
        logger.info(f"Updated description for topic: {topic}")
        return True

    def update_async(self, topic: str, async_execution: bool) -> bool:
        """
        Update the async execution setting of a topic handler.

        Args:
            topic: The topic name
            async_execution: New async setting

        Returns:
            True if updated, False if topic doesn't exist
        """
        if topic not in self._handlers:
            return False

        self._handlers[topic]["async"] = async_execution
        logger.info(f"Updated async setting for topic: {topic}")
        return True

    def get(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        Get handler info including the function for a specific topic.

        Args:
            topic: The topic name

        Returns:
            Handler info dict with function, or None if not found
        """
        if topic not in self._handlers:
            return None
        return self._handlers[topic]

    def get_all(self) -> Dict[str, Any]:
        """
        Get all registered topic handlers.

        Returns:
            Dictionary of topic -> handler info (without the actual function)
        """
        topics = {}
        for topic, info in self._handlers.items():
            topics[topic] = {
                "description": info.get("description", ""),
                "async": info.get("async", False),
                "registered_at": info.get("registered_at", ""),
                "handler_type": info.get("handler_type", "function"),
                "http_config": info.get("http_config"),
            }
        return topics

    def exists(self, topic: str) -> bool:
        """Check if a topic handler exists."""
        return topic in self._handlers

    def execute(
        self,
        instance_id: str,
        topic: str,
        variables: Dict[str, Any],
        loop_idx: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a service task handler.

        Args:
            instance_id: The process instance ID
            topic: The topic to execute
            variables: Current process variables
            loop_idx: Loop instance index (for multi-instance activities)

        Returns:
            Updated variables after handler execution

        Raises:
            ValueError: If no handler is registered for the topic
        """
        if topic not in self._handlers:
            raise ValueError(f"No handler registered for topic: {topic}")

        handler_info = self._handlers[topic]
        handler_function = handler_info["function"]

        logger.info(f"Executing service task {topic} for instance {instance_id}")

        try:
            # Try calling with loop_idx first
            updated_variables = handler_function(instance_id, variables, loop_idx)
            logger.info(f"Service task {topic} completed for instance {instance_id}")
            return updated_variables

        except TypeError:
            # Handler doesn't support loop_idx, try without it
            logger.debug(
                f"Handler for {topic} doesn't support loop_idx, trying without it"
            )
            try:
                updated_variables = handler_function(instance_id, variables)
                logger.info(
                    f"Service task {topic} completed for instance {instance_id}"
                )
                return updated_variables
            except Exception as e:
                logger.error(f"Service task {topic} failed: {e}")
                raise
        except Exception as e:
            logger.error(f"Service task {topic} failed for instance {instance_id}: {e}")
            raise

    def get_handler_info(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        Get info about a specific handler (without the function).

        Args:
            topic: The topic name

        Returns:
            Handler info dict, or None if not found
        """
        if topic not in self._handlers:
            return None

        info = self._handlers[topic]
        return {
            "description": info.get("description", ""),
            "async": info.get("async", False),
            "registered_at": info.get("registered_at", ""),
            "handler_type": info.get("handler_type", "function"),
            "http_config": info.get("http_config"),
        }

    def count(self) -> int:
        """Get the number of registered handlers."""
        return len(self._handlers)

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()
        logger.info("Cleared all topic handlers")
