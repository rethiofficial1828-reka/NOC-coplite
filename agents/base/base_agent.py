"""
Production-Quality Abstract Base Class for Atomic Agents.

Provides lifecycle management, schema validation, thread-safe metrics,
execution timing, exception propagation, and structured logging.
"""

from abc import ABC, abstractmethod
import threading
from typing import Any, Optional, Type

from agents.core.container import ServiceContainer
from agents.core.exceptions import AgentError, ExecutionError, ValidationError
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event_bus import EventBus
from agents.interfaces.agent_interface import IAgent
from agents.schemas.schemas import (
    AgentMetadata,
    AgentMetrics,
    AgentState,
    ExecutionContext,
)
from agents.utils.timing import ExecutionTimer


class BaseAgent(ABC, IAgent):
    """
    Abstract Base Class for all Atomic Agents in NOC Copilot.

    Supports dependency injection via ServiceContainer, event communication via EventBus,
    thread-safe metrics collection, input/output validation, and execution logging.
    """

    def __init__(
        self,
        metadata: AgentMetadata,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        """
        Initialize BaseAgent instance.

        Args:
            metadata: Agent identity, capabilities, and configuration.
            container: Optional ServiceContainer for dependency resolution.
            event_bus: Optional EventBus for publishing and subscribing to events.
        """
        if not metadata or not metadata.name:
            raise ValidationError("AgentMetadata with a non-empty name is required.")

        self._metadata = metadata
        self._container = container or ServiceContainer.get_global()
        self._event_bus = event_bus
        self._metrics = AgentMetrics(current_state=AgentState.UNINITIALIZED)
        self._logger = get_agent_logger(metadata.name)
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        """Unique identifier name of the agent."""
        return self._metadata.name

    @property
    def metadata(self) -> AgentMetadata:
        """Metadata describing the agent."""
        return self._metadata

    @property
    def metrics(self) -> AgentMetrics:
        """Copy or view of real-time agent execution metrics."""
        with self._lock:
            return self._metrics.model_copy()

    @property
    def status(self) -> str:
        """Current status string of the agent."""
        with self._lock:
            return self._metrics.current_state.value

    @property
    def container(self) -> ServiceContainer:
        """Dependency injection service container."""
        return self._container

    @property
    def event_bus(self) -> Optional[EventBus]:
        """Event bus instance used by the agent."""
        return self._event_bus

    def initialize(self) -> None:
        """
        Initialize agent resources. Transitions UNINITIALIZED -> INITIALIZING -> READY.
        """
        with self._lock:
            if self._metrics.current_state in (AgentState.READY, AgentState.RUNNING):
                return

            self._metrics.current_state = AgentState.INITIALIZING
            log_execution_event(
                self._logger,
                self.name,
                "INITIALIZING",
                f"Initializing agent '{self.name}' (v{self._metadata.version})",
            )

        try:
            self._initialize_internal()
            with self._lock:
                self._metrics.current_state = AgentState.READY
                log_execution_event(
                    self._logger,
                    self.name,
                    "READY",
                    f"Agent '{self.name}' successfully initialized and ready.",
                )
        except Exception as e:
            with self._lock:
                self._metrics.current_state = AgentState.FAILED
                log_execution_event(
                    self._logger,
                    self.name,
                    "INITIALIZATION_FAILED",
                    f"Failed to initialize agent '{self.name}': {e}",
                    level=40,  # logging.ERROR
                    exc_info=True,
                )
            raise ExecutionError(f"Initialization failed for agent '{self.name}': {e}") from e

    def _initialize_internal(self) -> None:
        """Subclasses can override this method to perform setup logic."""
        pass

    def validate_input(self, input_data: Any) -> Any:
        """
        Validate input payload prior to execution.

        Subclasses should override to provide custom validation logic or Pydantic parsing.
        """
        return input_data

    def validate_output(self, output_data: Any) -> Any:
        """
        Validate output payload post execution.

        Subclasses should override to provide custom validation logic.
        """
        return output_data

    def execute(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Any:
        """
        Execute the agent task with timing, metrics, validation, and error logging.

        Args:
            input_data: Payload required by the agent task.
            context: Optional shared ExecutionContext.

        Returns:
            Validated task output payload.

        Raises:
            ValidationError: If input or output validation fails.
            ExecutionError: If execution fails or an unhandled exception occurs.
        """
        with self._lock:
            if self._metrics.current_state == AgentState.UNINITIALIZED:
                self.initialize()
            elif self._metrics.current_state == AgentState.TERMINATED:
                raise ExecutionError(f"Cannot execute terminated agent '{self.name}'.")

            self._metrics.current_state = AgentState.RUNNING
            self._metrics.execution_count += 1

        log_execution_event(
            self._logger,
            self.name,
            "START",
            f"Starting execution of agent '{self.name}'",
        )

        timer = ExecutionTimer()
        try:
            with timer:
                validated_input = self.validate_input(input_data)
                raw_output = self._execute_internal(validated_input, context)
                validated_output = self.validate_output(raw_output)

            elapsed_ms = timer.elapsed_ms

            with self._lock:
                self._metrics.last_runtime_ms = elapsed_ms
                self._metrics.total_execution_time_ms += elapsed_ms
                self._metrics.success_count += 1
                if self._metrics.execution_count > 0:
                    self._metrics.average_runtime_ms = (
                        self._metrics.total_execution_time_ms / self._metrics.execution_count
                    )
                self._metrics.current_state = AgentState.READY

            log_execution_event(
                self._logger,
                self.name,
                "SUCCESS",
                f"Agent '{self.name}' executed successfully in {elapsed_ms:.2f}ms",
                exec_time_ms=elapsed_ms,
            )

            return validated_output

        except AgentError as ae:
            self._record_failure(ae)
            raise
        except Exception as e:
            wrapped_err = ExecutionError(f"Error executing agent '{self.name}': {e}")
            self._record_failure(wrapped_err)
            raise wrapped_err from e

    def _record_failure(self, error: Exception) -> None:
        """Helper to record failure metrics and log error event."""
        with self._lock:
            self._metrics.failure_count += 1
            self._metrics.current_state = AgentState.FAILED

        log_execution_event(
            self._logger,
            self.name,
            "FAILURE",
            f"Agent '{self.name}' execution failed: {error}",
            level=40,  # logging.ERROR
            exc_info=True,
        )

    @abstractmethod
    def _execute_internal(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Any:
        """
        Internal execution logic to be implemented by specific concrete agents.

        Args:
            input_data: Validated input payload.
            context: Optional workflow execution context.

        Returns:
            Task execution output.
        """
        pass

    def shutdown(self) -> None:
        """Gracefully release agent resources and transition to TERMINATED state."""
        with self._lock:
            if self._metrics.current_state == AgentState.TERMINATED:
                return
            self._metrics.current_state = AgentState.TERMINATED
            log_execution_event(
                self._logger,
                self.name,
                "TERMINATED",
                f"Agent '{self.name}' has been terminated.",
            )

    def reset_metrics(self) -> None:
        """Reset execution counters and metrics."""
        with self._lock:
            curr_state = self._metrics.current_state
            self._metrics = AgentMetrics(current_state=curr_state)
            log_execution_event(
                self._logger,
                self.name,
                "METRICS_RESET",
                f"Metrics reset for agent '{self.name}'.",
            )
