# Tests for Node Handlers
# Verifies execution of BPMN node types

import tempfile
import pytest
from rdflib import URIRef, RDF, Literal

from src.api.storage.base import BaseStorageService, INST, BPMN
from src.api.execution.node_handlers import NodeHandlers


class TestServiceTaskExecution:
    """Tests for service task execution."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        base.instances_graph.add((instance_uri, INST.status, Literal("RUNNING")))
        return instance_uri

    def _create_test_token(
        self, base: BaseStorageService, instance_uri: URIRef, node_uri: URIRef
    ):
        """Create a test token."""
        token_uri = INST["svc_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def _create_service_task(self, base: BaseStorageService, topic: str = None):
        """Create a service task definition."""
        task_uri = BPMN["ServiceTask1"]
        next_uri = BPMN["NextTask"]
        flow_uri = BPMN["Flow1"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        if topic:
            base.definitions_graph.add((task_uri, BPMN.topic, Literal(topic)))

        # Add outgoing flow
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, task_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, next_uri))
        base.definitions_graph.add((task_uri, BPMN.outgoing, flow_uri))

        return task_uri, next_uri

    def test_execute_service_task_with_topic(self):
        """Test executing a service task with a topic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, next_uri = self._create_service_task(base, "calculate_total")
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, task_uri)

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            # Track what was called
            topic_executed = []
            moved_to = []

            def get_vars(inst_id, loop_idx=None, mi_info=None):
                return {"amount": 100}

            def set_var(inst_id, name, value, loop_idx=None):
                pass

            def execute_topic(inst_id, topic, variables, loop_idx):
                topic_executed.append(topic)
                return {"total": variables["amount"] * 1.1}

            def get_mi_info(node_uri):
                return {"is_multi_instance": False}

            def move_token(inst, tok, inst_id):
                moved_to.append("moved")

            handler.execute_service_task(
                instance_uri,
                token_uri,
                task_uri,
                "test-inst",
                get_variables_callback=get_vars,
                set_variable_callback=set_var,
                execute_topic_callback=execute_topic,
                get_multi_instance_info_callback=get_mi_info,
                move_token_callback=move_token,
            )

            assert "calculate_total" in topic_executed
            assert len(moved_to) == 1

    def test_execute_service_task_no_topic(self):
        """Test executing a service task without a topic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_service_task(base)  # No topic
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, task_uri)

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            moved_to = []
            log_events = []

            def log_callback(inst, event_type, user, message):
                log_events.append(event_type)

            def move_token(inst, tok, inst_id):
                moved_to.append("moved")

            handler.execute_service_task(
                instance_uri,
                token_uri,
                task_uri,
                "test-inst",
                get_variables_callback=lambda *a, **k: {},
                set_variable_callback=lambda *a, **k: None,
                execute_topic_callback=lambda *a, **k: {},
                get_multi_instance_info_callback=lambda n: {"is_multi_instance": False},
                move_token_callback=move_token,
                log_callback=log_callback,
            )

            # Should still move token
            assert len(moved_to) == 1
            # Should log "SERVICE_TASK" with "no topic configured"
            assert "SERVICE_TASK" in log_events

    def test_service_task_handler_error(self):
        """Test service task execution when handler raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_service_task(base, "failing_topic")
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, task_uri)

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            moved_to = []

            def execute_topic(inst_id, topic, variables, loop_idx):
                raise RuntimeError("Handler failed")

            def move_token(inst, tok, inst_id):
                moved_to.append("moved")

            handler.execute_service_task(
                instance_uri,
                token_uri,
                task_uri,
                "test-inst",
                get_variables_callback=lambda *a, **k: {},
                set_variable_callback=lambda *a, **k: None,
                execute_topic_callback=execute_topic,
                get_multi_instance_info_callback=lambda n: {"is_multi_instance": False},
                move_token_callback=move_token,
            )

            # Token should be in ERROR status
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "ERROR"

            # Should NOT move token on error
            assert len(moved_to) == 0


class TestScriptTaskExecution:
    """Tests for script task execution."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        base.instances_graph.add((instance_uri, INST.status, Literal("RUNNING")))
        return instance_uri

    def _create_test_token(
        self, base: BaseStorageService, instance_uri: URIRef, node_uri: URIRef
    ):
        """Create a test token."""
        token_uri = INST["script_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def _create_script_task(
        self,
        base: BaseStorageService,
        script_code: str = None,
        script_format: str = None,
    ):
        """Create a script task definition."""
        task_uri = BPMN["ScriptTask1"]
        next_uri = BPMN["NextTask"]
        flow_uri = BPMN["ScriptFlow"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ScriptTask))
        if script_code:
            base.definitions_graph.add((task_uri, BPMN.script, Literal(script_code)))
        if script_format:
            base.definitions_graph.add(
                (task_uri, BPMN.scriptFormat, Literal(script_format))
            )

        # Add outgoing flow
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, task_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, next_uri))
        base.definitions_graph.add((task_uri, BPMN.outgoing, flow_uri))

        return task_uri, next_uri

    def test_script_task_disabled(self):
        """Test that script task is skipped when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_script_task(base, "result = 42")
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, task_uri)

            # Script tasks disabled by default
            handler = NodeHandlers(
                base.definitions_graph, base.instances_graph, script_tasks_enabled=False
            )

            moved_to = []
            log_events = []

            def move_token(inst, tok, inst_id):
                moved_to.append("moved")

            def log_callback(inst, event_type, user, message):
                log_events.append(event_type)

            handler.execute_script_task(
                instance_uri,
                token_uri,
                task_uri,
                "test-inst",
                get_variables_callback=lambda i: {},
                set_variable_callback=lambda *a: None,
                move_token_callback=move_token,
                log_callback=log_callback,
            )

            # Should still move token
            assert len(moved_to) == 1
            # Should log SCRIPT_TASK_DISABLED
            assert "SCRIPT_TASK_DISABLED" in log_events

    def test_script_task_no_content(self):
        """Test script task with no script content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_script_task(base)  # No script
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, task_uri)

            handler = NodeHandlers(
                base.definitions_graph, base.instances_graph, script_tasks_enabled=True
            )

            moved_to = []
            log_events = []

            def move_token(inst, tok, inst_id):
                moved_to.append("moved")

            def log_callback(inst, event_type, user, message):
                log_events.append(event_type)

            handler.execute_script_task(
                instance_uri,
                token_uri,
                task_uri,
                "test-inst",
                get_variables_callback=lambda i: {},
                set_variable_callback=lambda *a: None,
                move_token_callback=move_token,
                log_callback=log_callback,
            )

            # Should move token
            assert len(moved_to) == 1
            # Should log SCRIPT_TASK_SKIPPED
            assert "SCRIPT_TASK_SKIPPED" in log_events

    def test_script_task_execution(self):
        """Test script task execution when enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            script_code = "result = variables['input'] * 2"
            task_uri, _ = self._create_script_task(base, script_code)
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, task_uri)

            handler = NodeHandlers(
                base.definitions_graph, base.instances_graph, script_tasks_enabled=True
            )

            moved_to = []
            variables_set = {}

            def get_vars(inst_id):
                return {"input": 21}

            def set_var(inst_id, name, value):
                variables_set[name] = value

            def move_token(inst, tok, inst_id):
                moved_to.append("moved")

            handler.execute_script_task(
                instance_uri,
                token_uri,
                task_uri,
                "test-inst",
                get_variables_callback=get_vars,
                set_variable_callback=set_var,
                move_token_callback=move_token,
            )

            # Should move token
            assert len(moved_to) == 1
            # Should have set the result variable
            assert variables_set.get("result") == 42


class TestEventBasedGateway:
    """Tests for event-based gateway execution."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        base.instances_graph.add((instance_uri, INST.status, Literal("RUNNING")))
        return instance_uri

    def _create_test_token(
        self, base: BaseStorageService, instance_uri: URIRef, node_uri: URIRef
    ):
        """Create a test token."""
        token_uri = INST["gateway_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def _create_event_based_gateway(self, base: BaseStorageService):
        """Create an event-based gateway with receive task targets."""
        gateway_uri = BPMN["EventBasedGateway"]
        receive1_uri = BPMN["ReceiveTask1"]
        receive2_uri = BPMN["ReceiveTask2"]
        flow1_uri = BPMN["GatewayFlow1"]
        flow2_uri = BPMN["GatewayFlow2"]

        base.definitions_graph.add((gateway_uri, RDF.type, BPMN.EventBasedGateway))

        # First receive task
        base.definitions_graph.add((receive1_uri, RDF.type, BPMN.ReceiveTask))
        base.definitions_graph.add(
            (receive1_uri, BPMN.message, Literal("OrderReceived"))
        )

        # Second receive task
        base.definitions_graph.add((receive2_uri, RDF.type, BPMN.ReceiveTask))
        base.definitions_graph.add(
            (receive2_uri, BPMN.message, Literal("TimeoutExpired"))
        )

        # Flows from gateway
        base.definitions_graph.add((flow1_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow1_uri, BPMN.sourceRef, gateway_uri))
        base.definitions_graph.add((flow1_uri, BPMN.targetRef, receive1_uri))
        base.definitions_graph.add((gateway_uri, BPMN.outgoing, flow1_uri))

        base.definitions_graph.add((flow2_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow2_uri, BPMN.sourceRef, gateway_uri))
        base.definitions_graph.add((flow2_uri, BPMN.targetRef, receive2_uri))
        base.definitions_graph.add((gateway_uri, BPMN.outgoing, flow2_uri))

        return gateway_uri, receive1_uri, receive2_uri

    def test_event_based_gateway_creates_waiting_tokens(self):
        """Test that event-based gateway creates waiting tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri, receive1_uri, receive2_uri = self._create_event_based_gateway(
                base
            )
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, gateway_uri)

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            handler.execute_event_based_gateway(
                instance_uri, token_uri, gateway_uri, "test-inst"
            )

            # Original token should be consumed after spawning waiting tokens
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"

            # Should have created 2 waiting tokens at the receive tasks
            waiting_tokens = []
            for tok in base.instances_graph.objects(instance_uri, INST.hasToken):
                tok_status = base.instances_graph.value(tok, INST.status)
                tok_node = base.instances_graph.value(tok, INST.currentNode)
                if tok_status and str(tok_status) == "WAITING" and tok != token_uri:
                    waiting_tokens.append(tok_node)

            assert len(waiting_tokens) == 2
            assert receive1_uri in waiting_tokens
            assert receive2_uri in waiting_tokens

    def test_event_based_gateway_no_duplicate_waiting_tokens(self):
        """Test that event-based gateway does not duplicate waiting tokens."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri, receive1_uri, receive2_uri = self._create_event_based_gateway(
                base
            )
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, gateway_uri)

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            handler.execute_event_based_gateway(
                instance_uri, token_uri, gateway_uri, "test-inst"
            )

            second_token_uri = INST["gateway_token_2"]
            base.instances_graph.add((second_token_uri, RDF.type, INST.Token))
            base.instances_graph.add((second_token_uri, INST.belongsTo, instance_uri))
            base.instances_graph.add(
                (second_token_uri, INST.status, Literal("ACTIVE"))
            )
            base.instances_graph.add((second_token_uri, INST.currentNode, gateway_uri))
            base.instances_graph.add((instance_uri, INST.hasToken, second_token_uri))

            handler.execute_event_based_gateway(
                instance_uri, second_token_uri, gateway_uri, "test-inst"
            )

            waiting_tokens = []
            for tok in base.instances_graph.objects(instance_uri, INST.hasToken):
                tok_status = base.instances_graph.value(tok, INST.status)
                tok_node = base.instances_graph.value(tok, INST.currentNode)
                if tok_status and str(tok_status) == "WAITING":
                    waiting_tokens.append(tok_node)

            assert waiting_tokens.count(receive1_uri) == 1
            assert waiting_tokens.count(receive2_uri) == 1

    def test_event_based_gateway_no_targets(self):
        """Test event-based gateway with no outgoing targets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri = BPMN["EmptyGateway"]
            base.definitions_graph.add((gateway_uri, RDF.type, BPMN.EventBasedGateway))

            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, gateway_uri)

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            handler.execute_event_based_gateway(
                instance_uri, token_uri, gateway_uri, "test-inst"
            )

            # Token should be consumed
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"


class TestNodeTypeDetection:
    """Tests for node type detection."""

    def test_get_node_type(self):
        """Test getting node type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["TestTask"]
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            node_type = handler.get_node_type(task_uri)
            assert "ServiceTask" in node_type

    def test_is_end_event(self):
        """Test end event detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            end_uri = BPMN["EndEvent"]
            task_uri = BPMN["Task"]
            base.definitions_graph.add((end_uri, RDF.type, BPMN.EndEvent))
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            assert handler.is_end_event(end_uri) is True
            assert handler.is_end_event(task_uri) is False

    def test_is_start_event(self):
        """Test start event detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            start_uri = BPMN["StartEvent"]
            task_uri = BPMN["Task"]
            base.definitions_graph.add((start_uri, RDF.type, BPMN.StartEvent))
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            assert handler.is_start_event(start_uri) is True
            assert handler.is_start_event(task_uri) is False

    def test_is_gateway(self):
        """Test gateway detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            gateway_uri = BPMN["ExclusiveGateway"]
            task_uri = BPMN["Task"]
            base.definitions_graph.add((gateway_uri, RDF.type, BPMN.ExclusiveGateway))
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            assert handler.is_gateway(gateway_uri) is True
            assert handler.is_gateway(task_uri) is False

    def test_is_task(self):
        """Test task detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["UserTask"]
            gateway_uri = BPMN["Gateway"]
            base.definitions_graph.add((task_uri, RDF.type, BPMN.UserTask))
            base.definitions_graph.add((gateway_uri, RDF.type, BPMN.ExclusiveGateway))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            assert handler.is_task(task_uri) is True
            assert handler.is_task(gateway_uri) is False

    def test_is_subprocess(self):
        """Test subprocess detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            subprocess_uri = BPMN["SubProcess"]
            task_uri = BPMN["Task"]
            base.definitions_graph.add((subprocess_uri, RDF.type, BPMN.SubProcess))
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            assert handler.is_subprocess(subprocess_uri) is True
            assert handler.is_subprocess(task_uri) is False


class TestNodeHelpers:
    """Tests for node helper methods."""

    def test_get_outgoing_targets(self):
        """Test getting outgoing targets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["SourceTask"]
            target1_uri = BPMN["Target1"]
            target2_uri = BPMN["Target2"]
            flow1_uri = BPMN["Flow1"]
            flow2_uri = BPMN["Flow2"]

            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            base.definitions_graph.add((flow1_uri, RDF.type, BPMN.SequenceFlow))
            base.definitions_graph.add((flow1_uri, BPMN.sourceRef, task_uri))
            base.definitions_graph.add((flow1_uri, BPMN.targetRef, target1_uri))
            base.definitions_graph.add((task_uri, BPMN.outgoing, flow1_uri))

            base.definitions_graph.add((flow2_uri, RDF.type, BPMN.SequenceFlow))
            base.definitions_graph.add((flow2_uri, BPMN.sourceRef, task_uri))
            base.definitions_graph.add((flow2_uri, BPMN.targetRef, target2_uri))
            base.definitions_graph.add((task_uri, BPMN.outgoing, flow2_uri))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            targets = handler.get_outgoing_targets(task_uri)

            assert len(targets) == 2
            assert target1_uri in targets
            assert target2_uri in targets

    def test_get_incoming_sources(self):
        """Test getting incoming sources."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["TargetTask"]
            source1_uri = BPMN["Source1"]
            source2_uri = BPMN["Source2"]
            flow1_uri = BPMN["InFlow1"]
            flow2_uri = BPMN["InFlow2"]

            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            base.definitions_graph.add((flow1_uri, RDF.type, BPMN.SequenceFlow))
            base.definitions_graph.add((flow1_uri, BPMN.sourceRef, source1_uri))
            base.definitions_graph.add((flow1_uri, BPMN.targetRef, task_uri))
            base.definitions_graph.add((task_uri, BPMN.incoming, flow1_uri))

            base.definitions_graph.add((flow2_uri, RDF.type, BPMN.SequenceFlow))
            base.definitions_graph.add((flow2_uri, BPMN.sourceRef, source2_uri))
            base.definitions_graph.add((flow2_uri, BPMN.targetRef, task_uri))
            base.definitions_graph.add((task_uri, BPMN.incoming, flow2_uri))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            sources = handler.get_incoming_sources(task_uri)

            assert len(sources) == 2
            assert source1_uri in sources
            assert source2_uri in sources


class TestLoopIndex:
    """Tests for loop index handling."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        return instance_uri

    def test_get_loop_index_with_value(self):
        """Test getting loop index from token with loop instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = self._create_test_instance(base, "test-inst")

            token_uri = INST["loop_token"]
            base.instances_graph.add((token_uri, RDF.type, INST.Token))
            base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
            base.instances_graph.add((token_uri, INST.loopInstance, Literal("3")))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            loop_idx = handler._get_loop_index(token_uri)
            assert loop_idx == 3

    def test_get_loop_index_without_value(self):
        """Test getting loop index from token without loop instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = self._create_test_instance(base, "test-inst")

            token_uri = INST["regular_token"]
            base.instances_graph.add((token_uri, RDF.type, INST.Token))
            base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))

            handler = NodeHandlers(base.definitions_graph, base.instances_graph)

            loop_idx = handler._get_loop_index(token_uri)
            assert loop_idx is None
