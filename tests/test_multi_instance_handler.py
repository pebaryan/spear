# Tests for Multi-Instance Handler
# Verifies multi-instance (loop) activity execution

import tempfile
import pytest
from rdflib import URIRef, RDF, Literal

from src.api.storage.base import BaseStorageService, INST, BPMN
from src.api.execution.multi_instance import MultiInstanceHandler


class TestMultiInstanceInfo:
    """Tests for multi-instance configuration detection."""

    def _create_parallel_multi_instance_task(
        self, base: BaseStorageService, cardinality: int = 3
    ):
        """Create a task with parallel multi-instance configuration."""
        task_uri = BPMN["MultiInstanceTask"]
        loop_char_uri = BPMN["LoopCharacteristics1"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.loopCharacteristics, loop_char_uri))
        base.definitions_graph.add(
            (loop_char_uri, RDF.type, BPMN.MultiInstanceLoopCharacteristicsParallel)
        )
        base.definitions_graph.add(
            (loop_char_uri, BPMN.loopCardinality, Literal(str(cardinality)))
        )

        return task_uri

    def _create_sequential_multi_instance_task(
        self, base: BaseStorageService, cardinality: int = 3
    ):
        """Create a task with sequential multi-instance configuration."""
        task_uri = BPMN["SequentialTask"]
        loop_char_uri = BPMN["LoopCharacteristics2"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.loopCharacteristics, loop_char_uri))
        base.definitions_graph.add(
            (loop_char_uri, RDF.type, BPMN.MultiInstanceLoopCharacteristicsSequential)
        )
        base.definitions_graph.add(
            (loop_char_uri, BPMN.loopCardinality, Literal(str(cardinality)))
        )

        return task_uri

    def _create_data_driven_multi_instance_task(self, base: BaseStorageService):
        """Create a task with data input/output configuration."""
        task_uri = BPMN["DataDrivenTask"]
        loop_char_uri = BPMN["LoopCharacteristics3"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.loopCharacteristics, loop_char_uri))
        base.definitions_graph.add(
            (loop_char_uri, RDF.type, BPMN.MultiInstanceLoopCharacteristicsParallel)
        )
        base.definitions_graph.add((loop_char_uri, BPMN.dataInput, Literal("orderIds")))
        base.definitions_graph.add(
            (loop_char_uri, BPMN.dataOutput, Literal("processedOrder"))
        )

        return task_uri

    def test_detect_parallel_multi_instance(self):
        """Test detecting parallel multi-instance configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_parallel_multi_instance_task(base, cardinality=5)

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            info = handler.get_multi_instance_info(task_uri)

            assert info["is_multi_instance"] is True
            assert info["is_parallel"] is True
            assert info["is_sequential"] is False
            assert info["loop_cardinality"] == "5"

    def test_detect_sequential_multi_instance(self):
        """Test detecting sequential multi-instance configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_sequential_multi_instance_task(base, cardinality=4)

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            info = handler.get_multi_instance_info(task_uri)

            assert info["is_multi_instance"] is True
            assert info["is_parallel"] is False
            assert info["is_sequential"] is True
            assert info["loop_cardinality"] == "4"

    def test_detect_data_driven_multi_instance(self):
        """Test detecting data-driven multi-instance configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_data_driven_multi_instance_task(base)

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            info = handler.get_multi_instance_info(task_uri)

            assert info["is_multi_instance"] is True
            assert info["data_input"] == "orderIds"
            assert info["data_output"] == "processedOrder"

    def test_no_multi_instance(self):
        """Test detecting regular task (no multi-instance)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["RegularTask"]
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            info = handler.get_multi_instance_info(task_uri)

            assert info["is_multi_instance"] is False
            assert info["is_parallel"] is False
            assert info["is_sequential"] is False


class TestParallelMultiInstanceTokens:
    """Tests for parallel multi-instance token creation."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_test_token(
        self, base: BaseStorageService, instance_uri: URIRef, node_uri: URIRef
    ):
        """Create a test token."""
        token_uri = INST["original_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def _create_parallel_task(self, base: BaseStorageService, cardinality: int = 3):
        """Create a parallel multi-instance task."""
        task_uri = BPMN["ParallelTask"]
        loop_char_uri = BPMN["LoopChar1"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.loopCharacteristics, loop_char_uri))
        base.definitions_graph.add(
            (loop_char_uri, RDF.type, BPMN.MultiInstanceLoopCharacteristicsParallel)
        )
        base.definitions_graph.add(
            (loop_char_uri, BPMN.loopCardinality, Literal(str(cardinality)))
        )

        return task_uri

    def test_create_parallel_tokens(self):
        """Test creating parallel tokens for multi-instance activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_parallel_task(base, cardinality=4)
            instance_uri = self._create_test_instance(base, "test-inst")
            original_token = self._create_test_token(base, instance_uri, task_uri)

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            mi_info = handler.get_multi_instance_info(task_uri)
            created_tokens = handler.create_multi_instance_tokens(
                instance_uri, original_token, task_uri, "test-inst", mi_info
            )

            # Should create 4 tokens (cardinality)
            assert len(created_tokens) == 4

            # Each token should have a loop instance number
            for i, token in enumerate(created_tokens):
                loop_num = base.instances_graph.value(token, INST.loopInstance)
                assert loop_num is not None
                assert str(loop_num) == str(i)

            # Original token should be consumed
            status = base.instances_graph.value(original_token, INST.status)
            assert str(status) == "CONSUMED"

    def test_parallel_tokens_at_correct_node(self):
        """Test that parallel tokens are all at the correct node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_parallel_task(base, cardinality=3)
            instance_uri = self._create_test_instance(base, "test-inst")
            original_token = self._create_test_token(base, instance_uri, task_uri)

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            mi_info = handler.get_multi_instance_info(task_uri)
            created_tokens = handler.create_multi_instance_tokens(
                instance_uri, original_token, task_uri, "test-inst", mi_info
            )

            # All tokens should be at the task
            for token in created_tokens:
                current = base.instances_graph.value(token, INST.currentNode)
                assert current == task_uri


class TestSequentialMultiInstanceTokens:
    """Tests for sequential multi-instance token creation."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_test_token(
        self, base: BaseStorageService, instance_uri: URIRef, node_uri: URIRef
    ):
        """Create a test token."""
        token_uri = INST["seq_original_token"]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))
        return token_uri

    def _create_sequential_task(self, base: BaseStorageService, cardinality: int = 3):
        """Create a sequential multi-instance task."""
        task_uri = BPMN["SequentialTask"]
        loop_char_uri = BPMN["SeqLoopChar"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.loopCharacteristics, loop_char_uri))
        base.definitions_graph.add(
            (loop_char_uri, RDF.type, BPMN.MultiInstanceLoopCharacteristicsSequential)
        )
        base.definitions_graph.add(
            (loop_char_uri, BPMN.loopCardinality, Literal(str(cardinality)))
        )

        return task_uri

    def test_create_sequential_first_token(self):
        """Test creating first token for sequential multi-instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = self._create_sequential_task(base, cardinality=5)
            instance_uri = self._create_test_instance(base, "test-inst")
            original_token = self._create_test_token(base, instance_uri, task_uri)

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            mi_info = handler.get_multi_instance_info(task_uri)
            created_tokens = handler.create_multi_instance_tokens(
                instance_uri, original_token, task_uri, "test-inst", mi_info
            )

            # Should create only 1 token for sequential
            assert len(created_tokens) == 1

            # Token should be loop instance 0
            loop_num = base.instances_graph.value(created_tokens[0], INST.loopInstance)
            assert str(loop_num) == "0"

            # Token should have total count
            total = base.instances_graph.value(created_tokens[0], INST.loopTotal)
            assert str(total) == "5"


class TestLoopInstanceCompletion:
    """Tests for completing loop instances."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_loop_token(
        self,
        base: BaseStorageService,
        instance_uri: URIRef,
        node_uri: URIRef,
        loop_idx: int,
        total: int = None,
        token_id: str = None,
    ):
        """Create a loop token."""
        token_id = token_id or f"loop_token_{loop_idx}"
        token_uri = INST[token_id]
        base.instances_graph.add((token_uri, RDF.type, INST.Token))
        base.instances_graph.add((token_uri, INST.belongsTo, instance_uri))
        base.instances_graph.add((token_uri, INST.status, Literal("ACTIVE")))
        base.instances_graph.add((token_uri, INST.currentNode, node_uri))
        base.instances_graph.add((token_uri, INST.loopInstance, Literal(str(loop_idx))))
        base.instances_graph.add((instance_uri, INST.hasToken, token_uri))

        if total is not None:
            base.instances_graph.add((token_uri, INST.loopTotal, Literal(str(total))))

        return token_uri

    def _create_parallel_task_with_flow(self, base: BaseStorageService):
        """Create a parallel multi-instance task with outgoing flow."""
        task_uri = BPMN["CompletionTask"]
        next_uri = BPMN["NextTask"]
        flow_uri = BPMN["OutFlow"]
        loop_char_uri = BPMN["CompLoopChar"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.loopCharacteristics, loop_char_uri))
        base.definitions_graph.add(
            (loop_char_uri, RDF.type, BPMN.MultiInstanceLoopCharacteristicsParallel)
        )
        base.definitions_graph.add((loop_char_uri, BPMN.loopCardinality, Literal("3")))

        # Add outgoing flow
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, task_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, next_uri))
        base.definitions_graph.add((task_uri, BPMN.outgoing, flow_uri))

        return task_uri, next_uri

    def _create_sequential_task_with_flow(self, base: BaseStorageService):
        """Create a sequential multi-instance task with outgoing flow."""
        task_uri = BPMN["SeqCompletionTask"]
        next_uri = BPMN["SeqNextTask"]
        flow_uri = BPMN["SeqOutFlow"]
        loop_char_uri = BPMN["SeqCompLoopChar"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((task_uri, BPMN.loopCharacteristics, loop_char_uri))
        base.definitions_graph.add(
            (loop_char_uri, RDF.type, BPMN.MultiInstanceLoopCharacteristicsSequential)
        )
        base.definitions_graph.add((loop_char_uri, BPMN.loopCardinality, Literal("3")))

        # Add outgoing flow
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, task_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, next_uri))
        base.definitions_graph.add((task_uri, BPMN.outgoing, flow_uri))

        return task_uri, next_uri

    def test_parallel_completion_partial(self):
        """Test that partial parallel completion doesn't advance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_parallel_task_with_flow(base)
            instance_uri = self._create_test_instance(base, "test-inst")

            # Create 3 parallel tokens
            token0 = self._create_loop_token(
                base, instance_uri, task_uri, 0, token_id="par_token_0"
            )
            token1 = self._create_loop_token(
                base, instance_uri, task_uri, 1, token_id="par_token_1"
            )
            token2 = self._create_loop_token(
                base, instance_uri, task_uri, 2, token_id="par_token_2"
            )

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            mi_info = handler.get_multi_instance_info(task_uri)

            # Complete first token
            should_advance = handler.complete_loop_instance(
                instance_uri, token0, task_uri, "test-inst", mi_info
            )

            # Should not advance yet (only 1 of 3 complete)
            assert should_advance is False

    def test_sequential_creates_next_token(self):
        """Test that sequential completion creates next token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, _ = self._create_sequential_task_with_flow(base)
            instance_uri = self._create_test_instance(base, "test-inst")

            # Create first sequential token
            token0 = self._create_loop_token(
                base, instance_uri, task_uri, 0, total=3, token_id="seq_token_0"
            )

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            mi_info = handler.get_multi_instance_info(task_uri)

            # Complete first token
            should_advance = handler.complete_loop_instance(
                instance_uri, token0, task_uri, "test-inst", mi_info
            )

            # Should not advance (sequential creates next)
            assert should_advance is False

            # Original token should be consumed
            status = base.instances_graph.value(token0, INST.status)
            assert str(status) == "CONSUMED"

            # Should have created new token for instance 1
            found_next = False
            for token in base.instances_graph.objects(instance_uri, INST.hasToken):
                loop_num = base.instances_graph.value(token, INST.loopInstance)
                status = base.instances_graph.value(token, INST.status)
                if loop_num and str(loop_num) == "1" and str(status) == "ACTIVE":
                    found_next = True
                    break

            assert found_next is True

    def test_sequential_final_completes(self):
        """Test that completing final sequential instance advances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, next_uri = self._create_sequential_task_with_flow(base)
            instance_uri = self._create_test_instance(base, "test-inst")

            # Create final sequential token (index 2 of 3)
            token2 = self._create_loop_token(
                base, instance_uri, task_uri, 2, total=3, token_id="seq_final_token"
            )

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            mi_info = handler.get_multi_instance_info(task_uri)

            # Complete final token
            should_advance = handler.complete_loop_instance(
                instance_uri, token2, task_uri, "test-inst", mi_info
            )

            # Should advance (all complete)
            assert should_advance is True


class TestAdvancePastActivity:
    """Tests for advancing past a completed multi-instance activity."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def _create_task_with_outgoing(self, base: BaseStorageService):
        """Create a task with an outgoing flow."""
        task_uri = BPMN["AdvanceTask"]
        next_uri = BPMN["NextAfterAdvance"]
        flow_uri = BPMN["AdvanceFlow"]

        base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((next_uri, RDF.type, BPMN.ServiceTask))
        base.definitions_graph.add((flow_uri, RDF.type, BPMN.SequenceFlow))
        base.definitions_graph.add((flow_uri, BPMN.sourceRef, task_uri))
        base.definitions_graph.add((flow_uri, BPMN.targetRef, next_uri))
        base.definitions_graph.add((task_uri, BPMN.outgoing, flow_uri))

        return task_uri, next_uri

    def test_advance_creates_token_at_next(self):
        """Test that advancing creates token at next node."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri, next_uri = self._create_task_with_outgoing(base)
            instance_uri = self._create_test_instance(base, "test-inst")

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            new_token = handler.advance_past_activity(
                instance_uri, task_uri, "test-inst"
            )

            # Should have created a token
            assert new_token is not None

            # Token should be at next node
            current = base.instances_graph.value(new_token, INST.currentNode)
            assert current == next_uri

            # Token should be active
            status = base.instances_graph.value(new_token, INST.status)
            assert str(status) == "ACTIVE"

    def test_advance_no_outgoing(self):
        """Test advancing when there's no outgoing flow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            task_uri = BPMN["EndTask"]
            base.definitions_graph.add((task_uri, RDF.type, BPMN.ServiceTask))
            instance_uri = self._create_test_instance(base, "test-inst")

            handler = MultiInstanceHandler(base.definitions_graph, base.instances_graph)

            new_token = handler.advance_past_activity(
                instance_uri, task_uri, "test-inst"
            )

            # Should return None (no outgoing flow)
            assert new_token is None
