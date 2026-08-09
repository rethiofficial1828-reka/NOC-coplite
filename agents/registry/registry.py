"""
Thread-Safe Agent Registry with Lazy Loading & Dependency Validation.

Manages agent registration, resolution, duplicate checking, and dependency graph validation.
"""

import threading
from typing import Any, Callable, Dict, List, Optional, Type, Union

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import RegistrationError
from agents.core.logger import get_agent_logger
from agents.schemas.schemas import AgentMetadata

logger = get_agent_logger("AgentRegistry")


class AgentRegistrationRecord:
    """Internal storage record for an agent registration."""

    def __init__(
        self,
        name: str,
        target: Union[BaseAgent, Type[BaseAgent], Callable[..., BaseAgent]],
        metadata: Optional[AgentMetadata] = None,
    ) -> None:
        self.name = name
        self.target = target
        self.metadata = metadata
        self.instance: Optional[BaseAgent] = target if isinstance(target, BaseAgent) else None


class AgentRegistry:
    """
    Thread-safe registry for agent registration, lazy resolution, and dependency checking.
    """

    _global_instance: Optional["AgentRegistry"] = None
    _global_lock = threading.Lock()

    def __init__(self, container: Optional[ServiceContainer] = None) -> None:
        """
        Initialize AgentRegistry.

        Args:
            container: Optional ServiceContainer for lazy instance instantiation.
        """
        self._container = container or ServiceContainer.get_global()
        self._records: Dict[str, AgentRegistrationRecord] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "AgentRegistry":
        """Get or create global singleton AgentRegistry instance."""
        if cls._global_instance is None:
            with cls._global_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    def register(
        self,
        agent: Union[Type[BaseAgent], BaseAgent, Callable[..., BaseAgent]],
        name: Optional[str] = None,
        allow_override: bool = False,
    ) -> None:
        """
        Register an agent class, instance, or factory.

        Args:
            agent: BaseAgent subclass, instance, or factory callable returning BaseAgent.
            name: Optional explicit registration name. Inferred from agent if omitted.
            allow_override: If True, allows overwriting existing registration with same name.

        Raises:
            RegistrationError: If duplicate registration occurs or agent is invalid.
        """
        reg_name: str = ""
        metadata: Optional[AgentMetadata] = None

        if isinstance(agent, BaseAgent):
            reg_name = name or agent.name
            metadata = agent.metadata
        elif isinstance(agent, type) and issubclass(agent, BaseAgent):
            # Inspect class default metadata if available or instantiate mock metadata
            reg_name = name or agent.__name__
        elif callable(agent):
            if not name:
                raise RegistrationError("Factory callables require an explicit 'name' parameter.")
            reg_name = name
        else:
            raise RegistrationError(f"Cannot register invalid agent target: {agent}")

        with self._lock:
            if reg_name in self._records and not allow_override:
                raise RegistrationError(
                    f"Agent with name '{reg_name}' is already registered in AgentRegistry."
                )

            record = AgentRegistrationRecord(name=reg_name, target=agent, metadata=metadata)
            self._records[reg_name] = record

        logger.info(f"Registered agent '{reg_name}' in AgentRegistry.")

    def unregister(self, name: str) -> None:
        """
        Unregister an agent by name.

        Args:
            name: Name of agent to unregister.
        """
        with self._lock:
            if name in self._records:
                del self._records[name]
                logger.info(f"Unregistered agent '{name}' from AgentRegistry.")

    def exists(self, name: str) -> bool:
        """Check if an agent is registered by name."""
        with self._lock:
            return name in self._records

    def get(self, name: str) -> BaseAgent:
        """
        Retrieve and resolve an agent instance by name. Supports lazy instantiation.

        Args:
            name: Name of registered agent.

        Returns:
            Resolved BaseAgent instance.

        Raises:
            RegistrationError: If agent is not registered or instantiation fails.
        """
        with self._lock:
            if name not in self._records:
                raise RegistrationError(f"Agent '{name}' is not registered in AgentRegistry.")

            record = self._records[name]
            if record.instance is not None:
                return record.instance

            # Lazy instantiation
            target = record.target
            try:
                if isinstance(target, type) and issubclass(target, BaseAgent):
                    # Check if factory or instance can be created via container or default constructor
                    instance = target(
                        metadata=AgentMetadata(name=name), container=self._container
                    )
                elif callable(target):
                    instance = target(container=self._container)
                else:
                    raise RegistrationError(f"Invalid agent target for '{name}': {target}")

                if not isinstance(instance, BaseAgent):
                    raise RegistrationError(
                        f"Target for '{name}' did not produce a BaseAgent instance."
                    )

                record.instance = instance
                record.metadata = instance.metadata
                return instance

            except Exception as e:
                raise RegistrationError(f"Failed to instantiate lazy agent '{name}': {e}") from e

    def validate_dependencies(self, name: str) -> bool:
        """
        Validate that all prerequisite dependencies for an agent are registered.

        Args:
            name: Name of agent to validate.

        Returns:
            True if all dependencies are satisfied.

        Raises:
            RegistrationError: If missing dependency is found.
        """
        agent = self.get(name)
        deps = agent.metadata.dependencies
        with self._lock:
            missing = [dep for dep in deps if dep not in self._records]
            if missing:
                raise RegistrationError(
                    f"Agent '{name}' has missing required dependencies: {missing}"
                )
        return True

    def list_agents(self) -> Dict[str, Dict[str, Any]]:
        """
        List all registered agents alongside their metadata and metrics.

        Returns:
            Dict mapping agent name to summary dict of metadata and metrics.
        """
        result: Dict[str, Dict[str, Any]] = {}
        with self._lock:
            for name, record in self._records.items():
                if record.instance is not None:
                    meta_dict = record.instance.metadata.model_dump()
                    metrics_dict = record.instance.metrics.model_dump()
                else:
                    meta_dict = (
                        record.metadata.model_dump() if record.metadata else {"name": name}
                    )
                    metrics_dict = {"status": "UNINITIALIZED"}

                result[name] = {
                    "name": name,
                    "metadata": meta_dict,
                    "metrics": metrics_dict,
                    "is_instantiated": record.instance is not None,
                }
        return result

    def clear(self) -> None:
        """Clear all registered agents."""
        with self._lock:
            self._records.clear()
            logger.info("Cleared all registrations from AgentRegistry.")
