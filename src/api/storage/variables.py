# Variables Service for SPEAR Engine
# Handles process instance variable management with loop-scoping support

import logging
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from rdflib import URIRef, Literal

from .base import BaseStorageService, INST, VAR

if TYPE_CHECKING:
    from rdflib import Graph

logger = logging.getLogger(__name__)


class VariablesService:
    """
    Service for managing process instance variables.

    Supports:
    - Basic variable get/set operations
    - Loop-scoped variables for multi-instance activities
    - Multi-instance data input/output handling

    Variables are stored as RDF triples in the instances_graph:
    - instance hasVariable variable
    - variable name "variableName"
    - variable value "variableValue"

    Loop-scoped variables are named with the pattern: "varName_loop0", "varName_loop1", etc.
    """

    def __init__(self, base_storage: BaseStorageService):
        """
        Initialize the variables service.

        Args:
            base_storage: The base storage service providing graph access
        """
        self._storage = base_storage

    @property
    def _graph(self) -> "Graph":
        """Get the instances graph."""
        return self._storage.instances_graph

    # ==================== Loop Scope Utilities ====================

    def get_loop_scoped_name(self, base_name: str, loop_idx: int) -> str:
        """
        Convert a variable name to its loop-scoped version.

        Example: "orderId" with loop_idx=0 becomes "orderId_loop0"

        Args:
            base_name: The base variable name
            loop_idx: The loop instance index

        Returns:
            The loop-scoped variable name
        """
        return f"{base_name}_loop{loop_idx}"

    def parse_loop_scoped_name(self, scoped_name: str) -> Tuple[str, Optional[int]]:
        """
        Parse a loop-scoped variable name back to its components.

        Example: "orderId_loop0" becomes ("orderId", 0)
                "regularVar" becomes ("regularVar", None)

        Args:
            scoped_name: The potentially loop-scoped variable name

        Returns:
            Tuple of (base_name, loop_index) where loop_index is None
            if the name is not loop-scoped
        """
        if "_loop" in scoped_name:
            parts = scoped_name.rsplit("_loop", 1)
            if len(parts) == 2 and parts[1].isdigit():
                return parts[0], int(parts[1])
        return scoped_name, None

    def get_loop_index(self, token_uri: URIRef) -> Optional[int]:
        """
        Extract the loop index from a token.

        Args:
            token_uri: URI of the token

        Returns:
            The loop index, or None if the token is not part of a loop
        """
        loop_idx = self._graph.value(token_uri, INST.loopInstance)
        if loop_idx:
            try:
                return int(str(loop_idx))
            except ValueError:
                pass
        return None

    # ==================== Variable Operations ====================

    def get_variables(
        self,
        instance_id: str,
        loop_idx: Optional[int] = None,
        mi_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get variables for a process instance.

        Args:
            instance_id: ID of the process instance
            loop_idx: Optional loop index to scope variables to
            mi_info: Optional multi-instance info with data_input/data_output

        Returns:
            Dictionary of variable names to values
        """
        instance_uri = INST[instance_id]
        variables = {}

        # Collect all variables for the instance
        for var_uri in self._graph.objects(instance_uri, INST.hasVariable):
            name = self._graph.value(var_uri, VAR.name)
            value = self._graph.value(var_uri, VAR.value)

            if name and value:
                name_str = str(name)
                value_str = str(value)

                if loop_idx is not None:
                    # When scoped to a loop, include:
                    # 1. Variables scoped to this specific loop
                    # 2. Global (non-scoped) variables
                    base_name, var_loop_idx = self.parse_loop_scoped_name(name_str)
                    if var_loop_idx == loop_idx:
                        # This is a variable for our loop instance
                        variables[base_name] = value_str
                    elif var_loop_idx is None:
                        # This is a global variable
                        variables[name_str] = value_str
                else:
                    # No loop scope - return all variables as-is
                    variables[name_str] = value_str

        # Handle multi-instance data input/output
        if loop_idx is not None and mi_info and mi_info.get("data_input"):
            self._add_multi_instance_item(instance_uri, variables, loop_idx, mi_info)

        return variables

    def _add_multi_instance_item(
        self,
        instance_uri: URIRef,
        variables: Dict[str, Any],
        loop_idx: int,
        mi_info: Dict[str, Any],
    ) -> None:
        """
        Add the current item from a multi-instance collection to variables.

        For multi-instance activities with a data input collection,
        this extracts the item at the current loop index.

        Args:
            instance_uri: URI of the instance
            variables: Variables dict to update
            loop_idx: Current loop index
            mi_info: Multi-instance configuration info
        """
        data_input = mi_info["data_input"]
        data_output = mi_info.get("data_output", "item")

        # First try loop-scoped variable
        input_var_name_scoped = f"{data_input}_loop{loop_idx}"
        input_value = None

        for var_uri in self._graph.objects(instance_uri, INST.hasVariable):
            name = self._graph.value(var_uri, VAR.name)
            if name and str(name) == input_var_name_scoped:
                value = self._graph.value(var_uri, VAR.value)
                if value:
                    input_value = str(value)
                break

        # If not found, try non-scoped variable
        if input_value is None:
            for var_uri in self._graph.objects(instance_uri, INST.hasVariable):
                name = self._graph.value(var_uri, VAR.name)
                if name and str(name) == data_input:
                    value = self._graph.value(var_uri, VAR.value)
                    if value:
                        input_value = str(value)
                    break

        # Extract item at loop index from comma-separated collection
        if input_value:
            items = input_value.split(",")
            if loop_idx < len(items):
                variables[data_output] = items[loop_idx].strip()

    def set_variable(
        self,
        instance_id: str,
        name: str,
        value: Any,
        loop_idx: Optional[int] = None,
        save: bool = True,
    ) -> bool:
        """
        Set a variable on a process instance.

        Args:
            instance_id: ID of the process instance
            name: Variable name
            value: Variable value (will be converted to string)
            loop_idx: Optional loop index to scope the variable to
            save: Whether to persist immediately (default True)

        Returns:
            True if successful
        """
        instance_uri = INST[instance_id]

        # Build the variable name (with loop scope if specified)
        if loop_idx is not None:
            var_name = self.get_loop_scoped_name(name, loop_idx)
        else:
            var_name = name

        # Find existing variable
        var_uri = None
        for v in self._graph.objects(instance_uri, INST.hasVariable):
            if self._graph.value(v, VAR.name) == Literal(var_name):
                var_uri = v
                break

        if var_uri:
            # Update existing variable
            self._graph.set((var_uri, VAR.value, Literal(str(value))))
            logger.debug(f"Updated variable {var_name}={value} on {instance_id}")
        else:
            # Create new variable
            var_uri = VAR[f"{instance_id}_{var_name}"]
            self._graph.add((instance_uri, INST.hasVariable, var_uri))
            self._graph.add((var_uri, VAR.name, Literal(var_name)))
            self._graph.add((var_uri, VAR.value, Literal(str(value))))
            logger.debug(f"Created variable {var_name}={value} on {instance_id}")

        if save:
            self._storage.save_instances()

        return True

    def delete_variable(
        self,
        instance_id: str,
        name: str,
        loop_idx: Optional[int] = None,
        save: bool = True,
    ) -> bool:
        """
        Delete a variable from a process instance.

        Args:
            instance_id: ID of the process instance
            name: Variable name
            loop_idx: Optional loop index if the variable is loop-scoped
            save: Whether to persist immediately (default True)

        Returns:
            True if the variable was found and deleted, False otherwise
        """
        instance_uri = INST[instance_id]

        # Build the variable name
        if loop_idx is not None:
            var_name = self.get_loop_scoped_name(name, loop_idx)
        else:
            var_name = name

        # Find the variable
        var_uri = None
        for v in self._graph.objects(instance_uri, INST.hasVariable):
            if self._graph.value(v, VAR.name) == Literal(var_name):
                var_uri = v
                break

        if var_uri:
            # Remove variable reference from instance
            self._graph.remove((instance_uri, INST.hasVariable, var_uri))
            # Remove variable properties
            self._graph.remove((var_uri, None, None))

            if save:
                self._storage.save_instances()

            logger.debug(f"Deleted variable {var_name} from {instance_id}")
            return True

        return False

    def get_variable(
        self,
        instance_id: str,
        name: str,
        loop_idx: Optional[int] = None,
        default: Any = None,
    ) -> Any:
        """
        Get a single variable value.

        Args:
            instance_id: ID of the process instance
            name: Variable name
            loop_idx: Optional loop index if the variable is loop-scoped
            default: Default value if variable not found

        Returns:
            The variable value, or default if not found
        """
        instance_uri = INST[instance_id]

        # Build the variable name
        if loop_idx is not None:
            var_name = self.get_loop_scoped_name(name, loop_idx)
        else:
            var_name = name

        # Find the variable
        for var_uri in self._graph.objects(instance_uri, INST.hasVariable):
            if self._graph.value(var_uri, VAR.name) == Literal(var_name):
                value = self._graph.value(var_uri, VAR.value)
                if value:
                    return str(value)

        return default

    def set_variables_batch(
        self,
        instance_id: str,
        variables: Dict[str, Any],
        loop_idx: Optional[int] = None,
    ) -> int:
        """
        Set multiple variables at once, with a single save.

        Args:
            instance_id: ID of the process instance
            variables: Dictionary of variable names to values
            loop_idx: Optional loop index to scope all variables to

        Returns:
            Number of variables set
        """
        count = 0
        for name, value in variables.items():
            self.set_variable(instance_id, name, value, loop_idx, save=False)
            count += 1

        self._storage.save_instances()
        return count

    def delete_all_instance_variables(self, instance_id: str) -> int:
        """
        Delete all variables for an instance.

        Args:
            instance_id: ID of the process instance

        Returns:
            Number of variables deleted
        """
        instance_uri = INST[instance_id]
        deleted_count = 0

        # Find all variable URIs
        var_uris = list(self._graph.objects(instance_uri, INST.hasVariable))

        for var_uri in var_uris:
            self._graph.remove((instance_uri, INST.hasVariable, var_uri))
            self._graph.remove((var_uri, None, None))
            deleted_count += 1

        if deleted_count > 0:
            self._storage.save_instances()
            logger.info(
                f"Deleted {deleted_count} variables from instance {instance_id}"
            )

        return deleted_count

    def get_variable_names(
        self,
        instance_id: str,
        include_loop_scoped: bool = True,
    ) -> list:
        """
        Get a list of all variable names for an instance.

        Args:
            instance_id: ID of the process instance
            include_loop_scoped: Whether to include loop-scoped variables

        Returns:
            List of variable names
        """
        instance_uri = INST[instance_id]
        names = []

        for var_uri in self._graph.objects(instance_uri, INST.hasVariable):
            name = self._graph.value(var_uri, VAR.name)
            if name:
                name_str = str(name)
                if include_loop_scoped or "_loop" not in name_str:
                    names.append(name_str)

        return sorted(names)
