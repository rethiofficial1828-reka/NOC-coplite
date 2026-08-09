"""
Central Agent Orchestrator with Directed Acyclic Graph (DAG) Dependency Ordering.

Manages multi-agent workflow execution, dependency resolution, execution context,
and error propagation without coupling to concrete agent implementations.
"""

from collections import defaultdict, deque
import threading
from typing import Any, Dict, List, Optional, Set

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ExecutionError, RegistrationError
from agents.core.logger import get_agent_logger, log_execution_event
from agents.events.event_bus import EventBus
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import ExecutionContext

logger = get_agent_logger("AgentOrchestrator")


class AgentOrchestrator:
    """
    Central workflow orchestrator for Atomic Agents.

    Supports workflow registration, topological dependency ordering, step execution,
    shared execution context propagation, and structured logging.
    """

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        event_bus: Optional[EventBus] = None,
        container: Optional[ServiceContainer] = None,
    ) -> None:
        """
        Initialize AgentOrchestrator.

        Args:
            registry: AgentRegistry instance (defaults to global instance).
            event_bus: EventBus instance (defaults to global instance).
            container: ServiceContainer instance (defaults to global instance).
        """
        self._registry = registry or AgentRegistry.get_global()
        self._event_bus = event_bus or EventBus.get_global()
        self._container = container or ServiceContainer.get_global()
        self._workflows: Dict[str, List[str]] = {}
        self._lock = threading.RLock()

    @property
    def registry(self) -> AgentRegistry:
        """Agent registry instance."""
        return self._registry

    def register_workflow(self, workflow_name: str, agent_names: List[str]) -> None:
        """
        Register a named workflow consisting of a list of agent names.

        Args:
            workflow_name: Unique workflow identifier name.
            agent_names: List of registered agent names included in workflow.
        """
        if not workflow_name:
            raise ExecutionError("Workflow name cannot be empty.")
        if not agent_names:
            raise ExecutionError("Workflow agent_names list cannot be empty.")

        with self._lock:
            # Validate that all agents exist in registry
            for name in agent_names:
                if not self._registry.exists(name):
                    raise RegistrationError(
                        f"Cannot register workflow '{workflow_name}': agent '{name}' is not registered."
                    )
            self._workflows[workflow_name] = list(agent_names)

        logger.info(f"Registered workflow '{workflow_name}' with agents: {agent_names}")

    def resolve_dependency_order(self, agent_names: List[str]) -> List[str]:
        """
        Compute topological execution order for a set of agent names based on metadata dependencies.

        Args:
            agent_names: Target agent names to execute.

        Returns:
            Topologically sorted list of agent names.

        Raises:
            ExecutionError: If circular dependencies are detected or an agent is missing.
        """
        all_agents: Set[str] = set()

        def collect_deps(name: str) -> None:
            if name in all_agents:
                return
            if not self._registry.exists(name):
                raise ExecutionError(f"Required agent '{name}' is not registered.")
            all_agents.add(name)
            agent_inst = self._registry.get(name)
            for dep in agent_inst.metadata.dependencies:
                collect_deps(dep)

        for name in agent_names:
            collect_deps(name)

        # Build in-degree graph
        in_degree: Dict[str, int] = {name: 0 for name in all_agents}
        adj_list: Dict[str, List[str]] = defaultdict(list)

        for name in all_agents:
            agent_inst = self._registry.get(name)
            for dep in agent_inst.metadata.dependencies:
                adj_list[dep].append(name)
                in_degree[name] += 1

        # Kahn's algorithm for topological sorting
        queue = deque([name for name, deg in in_degree.items() if deg == 0])
        sorted_order: List[str] = []

        while queue:
            node = queue.popleft()
            sorted_order.append(node)
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(sorted_order) != len(all_agents):
            raise ExecutionError("Circular dependency detected in requested agent graph.")

        return sorted_order

    def execute_agent(
        self,
        agent_name: str,
        input_data: Any,
        context: Optional[ExecutionContext] = None,
    ) -> Any:
        """
        Invoke a single registered agent by name.

        Args:
            agent_name: Name of registered agent.
            input_data: Input payload.
            context: Optional shared ExecutionContext.

        Returns:
            Output payload returned by agent execution.
        """
        agent = self._registry.get(agent_name)
        log_execution_event(
            logger,
            agent_name,
            "ORCHESTRATOR_INVOKE",
            f"Orchestrator invoking agent '{agent_name}'",
        )
        return agent.execute(input_data, context=context)

    def execute_workflow(
        self,
        workflow_name: str,
        initial_input: Any = None,
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionContext:
        """
        Execute a registered workflow in topological dependency order.

        Args:
            workflow_name: Name of registered workflow.
            initial_input: Initial payload passed to the workflow root agents.
            context: Optional initial ExecutionContext.

        Returns:
            Final ExecutionContext containing results from all steps.

        Raises:
            ExecutionError: If workflow is not registered or step execution fails.
        """
        with self._lock:
            if workflow_name not in self._workflows:
                raise ExecutionError(f"Workflow '{workflow_name}' is not registered.")
            requested_agents = self._workflows[workflow_name]

        execution_order = self.resolve_dependency_order(requested_agents)
        ctx = context or ExecutionContext()
        ctx.parameters["workflow_name"] = workflow_name
        ctx.parameters["initial_input"] = initial_input

        logger.info(
            f"Executing workflow '{workflow_name}' in topological order: {execution_order}"
        )

        current_input = initial_input
        for agent_name in execution_order:
            try:
                # Execute agent and capture output
                output = self.execute_agent(agent_name, current_input, context=ctx)
                ctx.results[agent_name] = output
                current_input = output  # Pipeline output to next step
            except Exception as e:
                logger.error(
                    f"Workflow '{workflow_name}' failed at step '{agent_name}': {e}",
                    exc_info=True,
                )
                raise ExecutionError(
                    f"Workflow '{workflow_name}' failed at step '{agent_name}': {e}"
                ) from e

        logger.info(f"Workflow '{workflow_name}' completed successfully.")
        return ctx

    def list_workflows(self) -> Dict[str, List[str]]:
        """Return dict of registered workflows and their configured agent sequences."""
        with self._lock:
            return dict(self._workflows)
