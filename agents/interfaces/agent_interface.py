"""
Agent Interface Specification.

Defines abstract protocol contract for framework-independent agents.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class IAgent(Protocol):
    """
    Framework-agnostic interface protocol for all agent implementations.
    """

    @property
    def name(self) -> str:
        """Unique identifier name of the agent."""
        ...

    @property
    def status(self) -> str:
        """Current lifecycle execution status of the agent."""
        ...

    def validate_input(self, input_data: Any) -> Any:
        """Validate input payload before execution."""
        ...

    def validate_output(self, output_data: Any) -> Any:
        """Validate output payload after execution."""
        ...

    def execute(self, input_data: Any, context: Any = None) -> Any:
        """Execute the primary task of the agent."""
        ...
