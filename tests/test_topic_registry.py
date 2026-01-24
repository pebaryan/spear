# Tests for Topic Registry
# Verifies service task handler registration and execution

import pytest
from src.api.messaging.topic_registry import TopicRegistry


class TestTopicRegistration:
    """Tests for topic handler registration."""

    def test_register_handler(self):
        """Test registering a handler for a topic."""
        registry = TopicRegistry()

        def my_handler(instance_id, variables):
            return variables

        result = registry.register("my_topic", my_handler, description="My handler")

        assert result is True
        assert registry.exists("my_topic")

    def test_register_with_all_options(self):
        """Test registering with all configuration options."""
        registry = TopicRegistry()

        def my_handler(instance_id, variables):
            return variables

        result = registry.register(
            topic="full_topic",
            handler_function=my_handler,
            description="Full handler",
            async_execution=True,
            handler_type="http",
            http_config={"url": "http://example.com", "method": "POST"},
        )

        assert result is True

        info = registry.get_handler_info("full_topic")
        assert info is not None
        assert info["description"] == "Full handler"
        assert info["async"] is True
        assert info["handler_type"] == "http"
        assert info["http_config"]["url"] == "http://example.com"

    def test_unregister_handler(self):
        """Test unregistering a handler."""
        registry = TopicRegistry()

        def my_handler(instance_id, variables):
            return variables

        registry.register("to_remove", my_handler)
        assert registry.exists("to_remove")

        result = registry.unregister("to_remove")
        assert result is True
        assert not registry.exists("to_remove")

    def test_unregister_nonexistent(self):
        """Test unregistering a handler that doesn't exist."""
        registry = TopicRegistry()

        result = registry.unregister("nonexistent")
        assert result is False

    def test_exists(self):
        """Test checking if a topic exists."""
        registry = TopicRegistry()

        def my_handler(instance_id, variables):
            return variables

        registry.register("exists_topic", my_handler)

        assert registry.exists("exists_topic") is True
        assert registry.exists("nonexistent") is False


class TestTopicUpdates:
    """Tests for updating topic handler properties."""

    def test_update_description(self):
        """Test updating handler description."""
        registry = TopicRegistry()

        def my_handler(instance_id, variables):
            return variables

        registry.register("update_topic", my_handler, description="Original")

        result = registry.update_description("update_topic", "Updated")
        assert result is True

        info = registry.get_handler_info("update_topic")
        assert info["description"] == "Updated"

    def test_update_description_nonexistent(self):
        """Test updating description for nonexistent topic."""
        registry = TopicRegistry()

        result = registry.update_description("nonexistent", "Updated")
        assert result is False

    def test_update_async(self):
        """Test updating async execution setting."""
        registry = TopicRegistry()

        def my_handler(instance_id, variables):
            return variables

        registry.register("async_topic", my_handler, async_execution=False)

        result = registry.update_async("async_topic", True)
        assert result is True

        info = registry.get_handler_info("async_topic")
        assert info["async"] is True

    def test_update_async_nonexistent(self):
        """Test updating async for nonexistent topic."""
        registry = TopicRegistry()

        result = registry.update_async("nonexistent", True)
        assert result is False


class TestTopicRetrieval:
    """Tests for retrieving topic handlers."""

    def test_get_all(self):
        """Test getting all registered handlers."""
        registry = TopicRegistry()

        def handler1(instance_id, variables):
            return variables

        def handler2(instance_id, variables):
            return variables

        registry.register("topic1", handler1, description="Handler 1")
        registry.register("topic2", handler2, description="Handler 2")

        all_topics = registry.get_all()

        assert len(all_topics) == 2
        assert "topic1" in all_topics
        assert "topic2" in all_topics
        assert all_topics["topic1"]["description"] == "Handler 1"
        assert all_topics["topic2"]["description"] == "Handler 2"

    def test_get_all_excludes_function(self):
        """Test that get_all doesn't include the actual function."""
        registry = TopicRegistry()

        def secret_handler(instance_id, variables):
            return variables

        registry.register("secret_topic", secret_handler)

        all_topics = registry.get_all()

        # Should not include the function
        assert "function" not in all_topics["secret_topic"]

    def test_get_handler_info(self):
        """Test getting info for a specific handler."""
        registry = TopicRegistry()

        def my_handler(instance_id, variables):
            return variables

        registry.register(
            "info_topic",
            my_handler,
            description="Info handler",
            async_execution=True,
            handler_type="script",
        )

        info = registry.get_handler_info("info_topic")

        assert info is not None
        assert info["description"] == "Info handler"
        assert info["async"] is True
        assert info["handler_type"] == "script"
        assert "registered_at" in info

    def test_get_handler_info_nonexistent(self):
        """Test getting info for nonexistent handler."""
        registry = TopicRegistry()

        info = registry.get_handler_info("nonexistent")
        assert info is None

    def test_count(self):
        """Test counting registered handlers."""
        registry = TopicRegistry()

        def handler(instance_id, variables):
            return variables

        assert registry.count() == 0

        registry.register("topic1", handler)
        assert registry.count() == 1

        registry.register("topic2", handler)
        assert registry.count() == 2

        registry.unregister("topic1")
        assert registry.count() == 1

    def test_clear(self):
        """Test clearing all handlers."""
        registry = TopicRegistry()

        def handler(instance_id, variables):
            return variables

        registry.register("topic1", handler)
        registry.register("topic2", handler)
        registry.register("topic3", handler)

        assert registry.count() == 3

        registry.clear()

        assert registry.count() == 0
        assert not registry.exists("topic1")


class TestTopicExecution:
    """Tests for executing topic handlers."""

    def test_execute_handler(self):
        """Test executing a handler."""
        registry = TopicRegistry()

        def double_handler(instance_id, variables):
            variables["result"] = variables.get("value", 0) * 2
            return variables

        registry.register("double", double_handler)

        result = registry.execute("inst-123", "double", {"value": 5})

        assert result["result"] == 10

    def test_execute_handler_with_loop_idx(self):
        """Test executing a handler with loop index."""
        registry = TopicRegistry()

        def loop_handler(instance_id, variables, loop_idx):
            variables["loop_result"] = f"Loop {loop_idx}"
            return variables

        registry.register("loop_topic", loop_handler)

        result = registry.execute("inst-123", "loop_topic", {"value": 1}, loop_idx=3)

        assert result["loop_result"] == "Loop 3"

    def test_execute_handler_without_loop_idx_support(self):
        """Test executing a handler that doesn't support loop_idx."""
        registry = TopicRegistry()

        def simple_handler(instance_id, variables):
            variables["processed"] = True
            return variables

        registry.register("simple_topic", simple_handler)

        # Should fall back to calling without loop_idx
        result = registry.execute("inst-123", "simple_topic", {}, loop_idx=0)

        assert result["processed"] is True

    def test_execute_nonexistent_topic(self):
        """Test executing a nonexistent topic raises error."""
        registry = TopicRegistry()

        with pytest.raises(ValueError) as excinfo:
            registry.execute("inst-123", "nonexistent", {})

        assert "No handler registered for topic" in str(excinfo.value)

    def test_execute_handler_raises_error(self):
        """Test that handler errors are propagated."""
        registry = TopicRegistry()

        def error_handler(instance_id, variables):
            raise RuntimeError("Handler error")

        registry.register("error_topic", error_handler)

        with pytest.raises(RuntimeError) as excinfo:
            registry.execute("inst-123", "error_topic", {})

        assert "Handler error" in str(excinfo.value)

    def test_execute_modifies_variables(self):
        """Test that handler can modify multiple variables."""
        registry = TopicRegistry()

        def complex_handler(instance_id, variables):
            total = float(variables.get("amount", 0))
            tax = total * 0.1
            variables["tax"] = tax
            variables["grand_total"] = total + tax
            variables["instance"] = instance_id
            return variables

        registry.register("calculate", complex_handler)

        result = registry.execute("order-456", "calculate", {"amount": 100})

        assert result["tax"] == 10.0
        assert result["grand_total"] == 110.0
        assert result["instance"] == "order-456"


class TestMultipleRegistries:
    """Tests for multiple registry instances."""

    def test_registries_are_isolated(self):
        """Test that different registry instances are isolated."""
        registry1 = TopicRegistry()
        registry2 = TopicRegistry()

        def handler1(instance_id, variables):
            return {"source": "registry1"}

        def handler2(instance_id, variables):
            return {"source": "registry2"}

        registry1.register("shared_name", handler1)
        registry2.register("shared_name", handler2)

        result1 = registry1.execute("inst", "shared_name", {})
        result2 = registry2.execute("inst", "shared_name", {})

        assert result1["source"] == "registry1"
        assert result2["source"] == "registry2"

    def test_registry_counts_independent(self):
        """Test that registry counts are independent."""
        registry1 = TopicRegistry()
        registry2 = TopicRegistry()

        def handler(instance_id, variables):
            return variables

        registry1.register("topic1", handler)
        registry1.register("topic2", handler)
        registry2.register("topic3", handler)

        assert registry1.count() == 2
        assert registry2.count() == 1


class TestEdgeCases:
    """Tests for edge cases."""

    def test_register_overwrites_existing(self):
        """Test that registering same topic overwrites existing handler."""
        registry = TopicRegistry()

        def handler1(instance_id, variables):
            return {"version": 1}

        def handler2(instance_id, variables):
            return {"version": 2}

        registry.register("overwrite_topic", handler1)
        registry.register("overwrite_topic", handler2)

        result = registry.execute("inst", "overwrite_topic", {})

        assert result["version"] == 2
        assert registry.count() == 1

    def test_empty_topic_name(self):
        """Test handling of empty topic name."""
        registry = TopicRegistry()

        def handler(instance_id, variables):
            return variables

        # Empty string is a valid key in Python dicts
        registry.register("", handler)

        assert registry.exists("")
        result = registry.execute("inst", "", {})
        assert result == {}

    def test_special_characters_in_topic(self):
        """Test topics with special characters."""
        registry = TopicRegistry()

        def handler(instance_id, variables):
            return {"topic": "special"}

        registry.register("topic.with.dots", handler)
        registry.register("topic/with/slashes", handler)
        registry.register("topic-with-dashes", handler)

        assert registry.exists("topic.with.dots")
        assert registry.exists("topic/with/slashes")
        assert registry.exists("topic-with-dashes")

    def test_handler_returns_none(self):
        """Test handler that returns None."""
        registry = TopicRegistry()

        def none_handler(instance_id, variables):
            return None

        registry.register("none_topic", none_handler)

        result = registry.execute("inst", "none_topic", {})

        assert result is None

    def test_handler_returns_different_dict(self):
        """Test handler that returns completely different dict."""
        registry = TopicRegistry()

        def replace_handler(instance_id, variables):
            return {"completely": "different", "data": 123}

        registry.register("replace_topic", replace_handler)

        result = registry.execute("inst", "replace_topic", {"original": "data"})

        assert result == {"completely": "different", "data": 123}
        assert "original" not in result
