# Tests for Error Handler
# Verifies error, compensation, cancel, and terminate event handling

import tempfile
import pytest
from rdflib import URIRef, RDF, Literal

from src.api.storage.base import BaseStorageService, INST, BPMN
from src.api.execution.error_handler import ErrorHandler


class TestErrorEndEvent:
    """Tests for error end event handling."""

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
        token_uri = INST["test_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def _create_error_end_event(self, base: BaseStorageService, error_code: str = None):
        """Create an error end event definition."""
        node_uri = BPMN["ErrorEndEvent"]
        base.definitions_graph.add((node_uri, RDF.type, BPMN.ErrorEndEvent))
        if error_code:
            error_ref = BPMN[error_code]
            base.definitions_graph.add((node_uri, BPMN.errorRef, error_ref))
        return node_uri

    def test_execute_error_end_event(self):
        """Test executing an error end event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            node_uri = self._create_error_end_event(base, "PAYMENT_FAILED")
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, node_uri)

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            handler.execute_error_end_event(
                instance_uri, token_uri, node_uri, "test-inst"
            )

            # Token should be consumed
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"

            # Instance should be in ERROR status
            inst_status = base.instances_graph.value(instance_uri, INST.status)
            assert str(inst_status) == "ERROR"

    def test_error_end_event_with_variable_callback(self):
        """Test that error end event sets error variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            node_uri = self._create_error_end_event(base, "VALIDATION_ERROR")
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, node_uri)

            variables_set = {}

            def set_var(inst_id, name, value):
                variables_set[name] = value

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            handler.execute_error_end_event(
                instance_uri,
                token_uri,
                node_uri,
                "test-inst",
                set_variable_callback=set_var,
            )

            assert "errorCode" in variables_set
            assert "VALIDATION_ERROR" in variables_set["errorCode"]
            assert "errorNode" in variables_set


class TestCancelEndEvent:
    """Tests for cancel end event handling."""

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
        token_uri = INST["cancel_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_execute_cancel_end_event(self):
        """Test executing a cancel end event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            node_uri = BPMN["CancelEndEvent"]
            base.definitions_graph.add((node_uri, RDF.type, BPMN.CancelEndEvent))

            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, node_uri)

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            handler.execute_cancel_end_event(
                instance_uri, token_uri, node_uri, "test-inst"
            )

            # Token should be consumed
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"

            # Instance should be CANCELLED
            inst_status = base.instances_graph.value(instance_uri, INST.status)
            assert str(inst_status) == "CANCELLED"


class TestTerminateEndEvent:
    """Tests for terminate end event handling."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        base.instances_graph.add((instance_uri, INST.status, Literal("RUNNING")))
        return instance_uri

    def _create_test_token(
        self,
        base: BaseStorageService,
        instance_uri: URIRef,
        node_uri: URIRef,
        token_id: str = "term_token",
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

    def test_execute_terminate_end_event(self):
        """Test executing a terminate end event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            node_uri = BPMN["TerminateEndEvent"]
            other_node = BPMN["OtherTask"]
            base.definitions_graph.add((node_uri, RDF.type, BPMN.TerminateEndEvent))

            instance_uri = self._create_test_instance(base, "test-inst")
            terminate_token = self._create_test_token(
                base, instance_uri, node_uri, "term_token"
            )
            # Create other active tokens
            other_token1 = self._create_test_token(
                base, instance_uri, other_node, "other_token1", "ACTIVE"
            )
            other_token2 = self._create_test_token(
                base, instance_uri, other_node, "other_token2", "WAITING"
            )

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            handler.execute_terminate_end_event(
                instance_uri, terminate_token, node_uri, "test-inst"
            )

            # All tokens should be consumed
            for token in [terminate_token, other_token1, other_token2]:
                status = base.instances_graph.value(token, INST.status)
                assert str(status) == "CONSUMED"

            # Instance should be TERMINATED
            inst_status = base.instances_graph.value(instance_uri, INST.status)
            assert str(inst_status) == "TERMINATED"


class TestCompensationEndEvent:
    """Tests for compensation end event handling."""

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
        token_uri = INST["comp_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_execute_compensation_end_event(self):
        """Test executing a compensation end event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            node_uri = BPMN["CompensationEndEvent"]
            base.definitions_graph.add((node_uri, RDF.type, BPMN.CompensationEndEvent))

            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, node_uri)

            log_events = []

            def log_callback(inst, event_type, user, message):
                log_events.append({"event_type": event_type, "message": message})

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            handler.execute_compensation_end_event(
                instance_uri,
                token_uri,
                node_uri,
                "test-inst",
                log_callback=log_callback,
            )

            # Token should be consumed
            status = base.instances_graph.value(token_uri, INST.status)
            assert str(status) == "CONSUMED"

            # Should have logged the compensation event
            assert any(e["event_type"] == "COMPENSATION_END_EVENT" for e in log_events)


class TestBoundaryEvents:
    """Tests for boundary event execution."""

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
        token_uri = INST["boundary_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def _create_error_boundary_event(
        self,
        base: BaseStorageService,
        error_code: str = None,
        interrupting: bool = True,
    ):
        """Create an error boundary event."""
        node_uri = BPMN["ErrorBoundaryEvent"]
        next_uri = BPMN["ErrorHandler"]
        flow_uri = BPMN["ErrorFlow"]

        base.definitions_graph.add((node_uri, RDF.type, BPMN.ErrorBoundaryEvent))
        base.definitions_graph.add(
            (node_uri, BPMN.interrupting, Literal(str(interrupting).lower()))
        )
        if error_code:
            base.definitions_graph.add((node_uri, BPMN.errorRef, BPMN[error_code]))

        # Add outgoing flow
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, node_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, next_uri))
        base.definitions_graph.add((node_uri, BPMN.outgoing, flow_uri))

        return node_uri, next_uri

    def test_execute_error_boundary_event_interrupting(self):
        """Test executing an interrupting error boundary event."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            node_uri, next_uri = self._create_error_boundary_event(
                base, "ERROR_CODE", interrupting=True
            )
            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, node_uri)

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            handler.execute_boundary_event(
                instance_uri, token_uri, node_uri, "test-inst"
            )

            # Token should move to next node
            current = base.instances_graph.value(token_uri, INST.currentNode)
            assert current == next_uri

    def test_execute_timer_boundary_event_calls_move(self):
        """Test that timer boundary event calls move token callback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            node_uri = BPMN["TimerBoundaryEvent"]
            base.definitions_graph.add((node_uri, RDF.type, BPMN.TimerBoundaryEvent))

            instance_uri = self._create_test_instance(base, "test-inst")
            token_uri = self._create_test_token(base, instance_uri, node_uri)

            move_called = []

            def move_callback(inst, tok, inst_id):
                move_called.append(True)

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            handler.execute_boundary_event(
                instance_uri,
                token_uri,
                node_uri,
                "test-inst",
                move_token_callback=move_callback,
            )

            assert len(move_called) == 1


class TestGetBoundaryEvents:
    """Tests for getting boundary events attached to nodes."""

    def test_get_boundary_events_for_node(self):
        """Test getting boundary events attached to a node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)

            task_uri = BPMN["TaskWithBoundaries"]
            error_boundary = BPMN["ErrorBoundary"]
            timer_boundary = BPMN["TimerBoundary"]

            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
            base.definitions_graph.add(
                (task_uri, BPMN.hasBoundaryEvent, error_boundary)
            )
            base.definitions_graph.add(
                (task_uri, BPMN.hasBoundaryEvent, timer_boundary)
            )

            base.definitions_graph.add(
                (error_boundary, RDF.type, BPMN.ErrorBoundaryEvent)
            )
            base.definitions_graph.add((error_boundary, BPMN.errorRef, BPMN["ERR001"]))
            base.definitions_graph.add(
                (error_boundary, BPMN.interrupting, Literal("true"))
            )

            base.definitions_graph.add(
                (timer_boundary, RDF.type, BPMN.TimerBoundaryEvent)
            )
            base.definitions_graph.add(
                (timer_boundary, BPMN.interrupting, Literal("false"))
            )

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            events = handler.get_boundary_events_for_node(task_uri)

            assert len(events) == 2

            error_event = next(e for e in events if e["event_type"] == "error")
            assert error_event["is_interrupting"] is True
            assert "ERR001" in error_event["error_code"]

            timer_event = next(e for e in events if e["event_type"] == "timer")
            assert timer_event["is_interrupting"] is False


class TestExternalErrorThrow:
    """Tests for external error throwing API."""

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
        token_uri = INST["ext_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def test_throw_error_uncaught(self):
        """Test throwing an error that is not caught."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["Task"]
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            instance_uri = self._create_test_instance(base, "test-inst")
            self._create_test_token(base, instance_uri, task_uri)

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            result = handler.throw_error(
                "test-inst", "UNCAUGHT_ERROR", "Something went wrong"
            )

            assert result["status"] == "uncaught"
            assert result["caught_by_boundary_event"] is False

            # Instance should be in ERROR status
            inst_status = base.instances_graph.value(instance_uri, INST.status)
            assert str(inst_status) == "ERROR"

    def test_throw_error_instance_not_found(self):
        """Test throwing error for nonexistent instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            with pytest.raises(ValueError) as excinfo:
                handler.throw_error("nonexistent", "ERROR", "message")

            assert "not found" in str(excinfo.value)

    def test_throw_error_instance_not_running(self):
        """Test throwing error for completed instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = INST["completed-inst"]
            base.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
            base.instances_graph.add((instance_uri, INST.status, Literal("COMPLETED")))

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            with pytest.raises(ValueError) as excinfo:
                handler.throw_error("completed-inst", "ERROR", "message")

            assert "Cannot throw error" in str(excinfo.value)


class TestExternalCancelInstance:
    """Tests for external instance cancellation API."""

    def _create_test_instance(
        self, base: BaseStorageService, instance_id: str, status: str = "RUNNING"
    ):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, INST.ProcessInstance))
        base.instances_graph.add((instance_uri, INST.status, Literal(status)))
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

    def test_cancel_instance(self):
        """Test cancelling a running instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            instance_uri = self._create_test_instance(base, "test-inst")
            token1 = self._create_test_token(base, instance_uri, "token1", "ACTIVE")
            token2 = self._create_test_token(base, instance_uri, "token2", "WAITING")

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            result = handler.cancel_instance("test-inst", "User requested cancellation")

            assert result["status"] == "CANCELLED"

            # All tokens should be consumed
            status1 = base.instances_graph.value(token1, INST.status)
            status2 = base.instances_graph.value(token2, INST.status)
            assert str(status1) == "CONSUMED"
            assert str(status2) == "CONSUMED"

            # Instance should be CANCELLED
            inst_status = base.instances_graph.value(instance_uri, INST.status)
            assert str(inst_status) == "CANCELLED"

    def test_cancel_instance_not_found(self):
        """Test cancelling nonexistent instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            with pytest.raises(ValueError) as excinfo:
                handler.cancel_instance("nonexistent", "reason")

            assert "not found" in str(excinfo.value)

    def test_cancel_already_completed_instance(self):
        """Test cancelling already completed instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            self._create_test_instance(base, "completed-inst", "COMPLETED")

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            with pytest.raises(ValueError) as excinfo:
                handler.cancel_instance("completed-inst", "reason")

            assert "already" in str(excinfo.value)


class TestTransactionHandling:
    """Tests for transaction subprocess handling."""

    def test_find_enclosing_transaction(self):
        """Test finding enclosing transaction subprocess."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)

            # Create a transaction subprocess containing a task
            transaction_uri = BPMN["TransactionSubprocess"]
            task_uri = BPMN["TaskInTransaction"]

            base.definitions_graph.add(
                (transaction_uri, RDF.type, BPMN.TransactionSubProcess)
            )
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
            base.definitions_graph.add((task_uri, BPMN.hasParent, transaction_uri))

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            found = handler._find_enclosing_transaction(task_uri)

            assert found == transaction_uri

    def test_find_enclosing_transaction_not_found(self):
        """Test that no transaction is found for regular task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)

            task_uri = BPMN["RegularTask"]
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            handler = ErrorHandler(base.definitions_graph, base.instances_graph)

            found = handler._find_enclosing_transaction(task_uri)

            assert found is None
