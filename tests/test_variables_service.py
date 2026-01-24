# Tests for Variables Service
# Verifies process variable management with loop-scoping support

import os
import tempfile
import pytest
from rdflib import URIRef, RDF

from src.api.storage.base import BaseStorageService, INST, VAR, BPMN
from src.api.storage.variables import VariablesService


class TestVariablesService:
    """Tests for the VariablesService class."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Helper to create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def test_set_and_get_variable(self):
        """Test basic variable set and get."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set a variable
            result = vars_service.set_variable("test-instance", "orderId", "12345")
            assert result is True

            # Get the variable
            value = vars_service.get_variable("test-instance", "orderId")
            assert value == "12345"

    def test_get_nonexistent_variable(self):
        """Test getting a variable that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Get nonexistent variable with default
            value = vars_service.get_variable(
                "test-instance", "missing", default="default"
            )
            assert value == "default"

            # Get nonexistent variable without default
            value = vars_service.get_variable("test-instance", "missing")
            assert value is None

    def test_update_variable(self):
        """Test updating an existing variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set initial value
            vars_service.set_variable("test-instance", "counter", "1")
            assert vars_service.get_variable("test-instance", "counter") == "1"

            # Update value
            vars_service.set_variable("test-instance", "counter", "2")
            assert vars_service.get_variable("test-instance", "counter") == "2"

    def test_delete_variable(self):
        """Test deleting a variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set and verify variable exists
            vars_service.set_variable("test-instance", "toDelete", "value")
            assert vars_service.get_variable("test-instance", "toDelete") == "value"

            # Delete it
            result = vars_service.delete_variable("test-instance", "toDelete")
            assert result is True

            # Verify it's gone
            assert vars_service.get_variable("test-instance", "toDelete") is None

            # Try to delete again
            result = vars_service.delete_variable("test-instance", "toDelete")
            assert result is False

    def test_get_variables_all(self):
        """Test getting all variables for an instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set multiple variables
            vars_service.set_variable("test-instance", "var1", "value1")
            vars_service.set_variable("test-instance", "var2", "value2")
            vars_service.set_variable("test-instance", "var3", "value3")

            # Get all
            variables = vars_service.get_variables("test-instance")

            assert len(variables) == 3
            assert variables["var1"] == "value1"
            assert variables["var2"] == "value2"
            assert variables["var3"] == "value3"

    def test_set_variables_batch(self):
        """Test setting multiple variables at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set batch
            count = vars_service.set_variables_batch(
                "test-instance",
                {
                    "a": "1",
                    "b": "2",
                    "c": "3",
                },
            )

            assert count == 3

            variables = vars_service.get_variables("test-instance")
            assert variables["a"] == "1"
            assert variables["b"] == "2"
            assert variables["c"] == "3"

    def test_delete_all_instance_variables(self):
        """Test deleting all variables for an instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set multiple variables
            vars_service.set_variables_batch(
                "test-instance", {"a": "1", "b": "2", "c": "3"}
            )

            # Delete all
            count = vars_service.delete_all_instance_variables("test-instance")
            assert count == 3

            # Verify empty
            variables = vars_service.get_variables("test-instance")
            assert len(variables) == 0

    def test_get_variable_names(self):
        """Test getting list of variable names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            vars_service.set_variables_batch(
                "test-instance", {"alpha": "1", "beta": "2", "gamma": "3"}
            )

            names = vars_service.get_variable_names("test-instance")

            assert len(names) == 3
            assert "alpha" in names
            assert "beta" in names
            assert "gamma" in names
            # Should be sorted
            assert names == ["alpha", "beta", "gamma"]


class TestLoopScopedVariables:
    """Tests for loop-scoped variable functionality."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Helper to create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def test_loop_scoped_name_generation(self):
        """Test generating loop-scoped variable names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            assert vars_service.get_loop_scoped_name("orderId", 0) == "orderId_loop0"
            assert vars_service.get_loop_scoped_name("orderId", 1) == "orderId_loop1"
            assert vars_service.get_loop_scoped_name("orderId", 99) == "orderId_loop99"

    def test_parse_loop_scoped_name(self):
        """Test parsing loop-scoped variable names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            # Loop-scoped names
            assert vars_service.parse_loop_scoped_name("orderId_loop0") == (
                "orderId",
                0,
            )
            assert vars_service.parse_loop_scoped_name("orderId_loop5") == (
                "orderId",
                5,
            )

            # Non-scoped names
            assert vars_service.parse_loop_scoped_name("regularVar") == (
                "regularVar",
                None,
            )
            assert vars_service.parse_loop_scoped_name("has_underscore") == (
                "has_underscore",
                None,
            )

            # Edge cases
            assert vars_service.parse_loop_scoped_name("var_loopX") == (
                "var_loopX",
                None,
            )

    def test_set_and_get_loop_scoped_variable(self):
        """Test setting and getting loop-scoped variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set variables for different loop instances
            vars_service.set_variable("test-instance", "result", "value0", loop_idx=0)
            vars_service.set_variable("test-instance", "result", "value1", loop_idx=1)
            vars_service.set_variable("test-instance", "result", "value2", loop_idx=2)

            # Get for specific loop
            assert (
                vars_service.get_variable("test-instance", "result", loop_idx=0)
                == "value0"
            )
            assert (
                vars_service.get_variable("test-instance", "result", loop_idx=1)
                == "value1"
            )
            assert (
                vars_service.get_variable("test-instance", "result", loop_idx=2)
                == "value2"
            )

    def test_get_variables_with_loop_scope(self):
        """Test getting variables scoped to a specific loop instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set global variables
            vars_service.set_variable("test-instance", "globalVar", "global")

            # Set loop-scoped variables
            vars_service.set_variable(
                "test-instance", "loopVar", "loop0value", loop_idx=0
            )
            vars_service.set_variable(
                "test-instance", "loopVar", "loop1value", loop_idx=1
            )

            # Get for loop 0 - should include global and loop0
            vars_loop0 = vars_service.get_variables("test-instance", loop_idx=0)
            assert vars_loop0["globalVar"] == "global"
            assert vars_loop0["loopVar"] == "loop0value"
            assert "loopVar_loop1" not in vars_loop0

            # Get for loop 1 - should include global and loop1
            vars_loop1 = vars_service.get_variables("test-instance", loop_idx=1)
            assert vars_loop1["globalVar"] == "global"
            assert vars_loop1["loopVar"] == "loop1value"

    def test_get_variables_no_scope_includes_all(self):
        """Test that getting variables without scope includes all raw names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            vars_service.set_variable("test-instance", "globalVar", "global")
            vars_service.set_variable("test-instance", "loopVar", "loop0", loop_idx=0)
            vars_service.set_variable("test-instance", "loopVar", "loop1", loop_idx=1)

            # Get all (no scope)
            all_vars = vars_service.get_variables("test-instance")

            assert all_vars["globalVar"] == "global"
            assert all_vars["loopVar_loop0"] == "loop0"
            assert all_vars["loopVar_loop1"] == "loop1"

    def test_delete_loop_scoped_variable(self):
        """Test deleting loop-scoped variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            vars_service.set_variable("test-instance", "var", "loop0", loop_idx=0)
            vars_service.set_variable("test-instance", "var", "loop1", loop_idx=1)

            # Delete loop 0 variable
            result = vars_service.delete_variable("test-instance", "var", loop_idx=0)
            assert result is True

            # Loop 0 should be gone
            assert vars_service.get_variable("test-instance", "var", loop_idx=0) is None

            # Loop 1 should still exist
            assert (
                vars_service.get_variable("test-instance", "var", loop_idx=1) == "loop1"
            )

    def test_get_variable_names_exclude_loop_scoped(self):
        """Test filtering out loop-scoped variables from name list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            vars_service.set_variable("test-instance", "global", "value")
            vars_service.set_variable("test-instance", "scoped", "loop0", loop_idx=0)
            vars_service.set_variable("test-instance", "scoped", "loop1", loop_idx=1)

            # Include all
            all_names = vars_service.get_variable_names(
                "test-instance", include_loop_scoped=True
            )
            assert len(all_names) == 3

            # Exclude loop-scoped
            global_names = vars_service.get_variable_names(
                "test-instance", include_loop_scoped=False
            )
            assert len(global_names) == 1
            assert "global" in global_names


class TestMultiInstanceDataHandling:
    """Tests for multi-instance data input/output handling."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Helper to create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        return instance_uri

    def test_multi_instance_item_extraction(self):
        """Test extracting items from a collection for multi-instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            # Set a collection variable
            vars_service.set_variable("test-instance", "orderIds", "A001, B002, C003")

            mi_info = {"data_input": "orderIds", "data_output": "currentOrder"}

            # Get variables for each loop instance
            vars0 = vars_service.get_variables(
                "test-instance", loop_idx=0, mi_info=mi_info
            )
            assert vars0["currentOrder"] == "A001"

            vars1 = vars_service.get_variables(
                "test-instance", loop_idx=1, mi_info=mi_info
            )
            assert vars1["currentOrder"] == "B002"

            vars2 = vars_service.get_variables(
                "test-instance", loop_idx=2, mi_info=mi_info
            )
            assert vars2["currentOrder"] == "C003"

    def test_multi_instance_default_output_name(self):
        """Test that default output name is 'item' when not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)

            self._create_test_instance(base, "test-instance")

            vars_service.set_variable("test-instance", "items", "x, y, z")

            # No data_output specified - should default to "item"
            mi_info = {"data_input": "items"}

            vars0 = vars_service.get_variables(
                "test-instance", loop_idx=0, mi_info=mi_info
            )
            assert vars0["item"] == "x"


class TestPersistence:
    """Tests for variable persistence."""

    def _create_test_instance(self, base: BaseStorageService, instance_id: str):
        """Helper to create a test process instance."""
        instance_uri = INST[instance_id]
        base.instances_graph.add((instance_uri, RDF.type, BPMN.ProcessInstance))
        base.save_instances()
        return instance_uri

    def test_variables_persist_to_disk(self):
        """Test that variables are persisted to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set up with first service instance
            base1 = BaseStorageService(tmpdir)
            vars1 = VariablesService(base1)
            self._create_test_instance(base1, "test-instance")

            vars1.set_variable("test-instance", "persistent", "value")

            # Load with new service instance
            base2 = BaseStorageService(tmpdir)
            vars2 = VariablesService(base2)

            value = vars2.get_variable("test-instance", "persistent")
            assert value == "value"

    def test_set_variable_no_save(self):
        """Test setting variable without immediate persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = BaseStorageService(tmpdir)
            vars_service = VariablesService(base)
            self._create_test_instance(base, "test-instance")

            # Set without saving
            vars_service.set_variable("test-instance", "temp", "value", save=False)

            # In-memory should work
            assert vars_service.get_variable("test-instance", "temp") == "value"

            # New instance shouldn't see it
            base2 = BaseStorageService(tmpdir)
            vars2 = VariablesService(base2)
            assert vars2.get_variable("test-instance", "temp") is None

            # Now save
            base.save_instances()

            # New instance should see it
            base3 = BaseStorageService(tmpdir)
            vars3 = VariablesService(base3)
            assert vars3.get_variable("test-instance", "temp") == "value"
