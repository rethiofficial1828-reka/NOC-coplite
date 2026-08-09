"""
Execution Graph (DAG) for Enterprise AI Investigation Platform.

Represents an investigation workflow as a Directed Acyclic Graph (DAG) of Atomic Agent
nodes and dependency edges. Supports topological sorting, parallel execution grouping,
cycle detection, failure propagation, retries, and visualization metadata.
"""

from collections import defaultdict, deque
import threading
from typing import Any, Dict, List, Optional, Set

from agents.core.exceptions import ValidationError
from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_models import (
    DependencyType,
    ExecutionEdge,
    ExecutionGraphModel,
    ExecutionNode,
    InvestigationPlan,
    PlanStatus,
)

logger = get_agent_logger("ExecutionGraph")


class ExecutionGraph:
    """
    Thread-safe Directed Acyclic Graph (DAG) managing investigation node execution.
    """

    def __init__(self, request_id: str = "") -> None:
        self.graph_id = ""
        self.request_id = request_id
        self._nodes: Dict[str, ExecutionNode] = {}
        self._edges: List[ExecutionEdge] = []
        self._adjacency: Dict[str, List[str]] = defaultdict(list)  # src -> list of targets
        self._reverse_adj: Dict[str, List[str]] = defaultdict(list)  # target -> list of sources
        self._lock = threading.RLock()

    @classmethod
    def from_plan(cls, plan: InvestigationPlan) -> "ExecutionGraph":
        """
        Build an ExecutionGraph DAG directly from an InvestigationPlan.
        """
        graph = cls(request_id=plan.request_id)
        graph.graph_id = f"graph-{plan.plan_id}"

        # First pass: Add all nodes from stages
        for stage in plan.stages:
            for agent_plan in stage.agent_plans:
                node = ExecutionNode(
                    node_id=agent_plan.agent_name,
                    agent_name=agent_plan.agent_name,
                    dependencies=list(agent_plan.depends_on),
                    status=PlanStatus.PENDING,
                    max_retries=agent_plan.retry_count,
                    mandatory=agent_plan.mandatory,
                )
                graph.add_node(node)

        # Second pass: Add edges for explicit dependencies
        for node_id, node in graph.nodes.items():
            for dep in node.dependencies:
                if dep in graph.nodes:
                    graph.add_edge(dep, node_id, DependencyType.HARD)

        if graph.has_cycle():
            raise ValidationError(f"Invalid InvestigationPlan: execution graph contains cycles for request '{plan.request_id}'.")

        return graph

    @property
    def nodes(self) -> Dict[str, ExecutionNode]:
        """Copy of all nodes in the graph."""
        with self._lock:
            return {k: v.model_copy() for k, v in self._nodes.items()}

    @property
    def edges(self) -> List[ExecutionEdge]:
        """Copy of all edges in the graph."""
        with self._lock:
            return [e.model_copy() for e in self._edges]

    def add_node(self, node: ExecutionNode) -> None:
        """Add a node to the graph."""
        with self._lock:
            self._nodes[node.node_id] = node.model_copy()

    def add_edge(
        self,
        source_node: str,
        target_node: str,
        dependency_type: DependencyType = DependencyType.HARD,
    ) -> None:
        """Add a directed edge from source_node to target_node."""
        with self._lock:
            if source_node not in self._nodes or target_node not in self._nodes:
                raise ValidationError(f"Edge nodes '{source_node}' -> '{target_node}' must exist in graph.")

            edge = ExecutionEdge(
                source_node=source_node,
                target_node=target_node,
                dependency_type=dependency_type,
            )
            self._edges.append(edge)
            self._adjacency[source_node].append(target_node)
            self._reverse_adj[target_node].append(source_node)

            # Update dependencies list on node
            if source_node not in self._nodes[target_node].dependencies:
                self._nodes[target_node].dependencies.append(source_node)

    def get_node(self, node_id: str) -> Optional[ExecutionNode]:
        """Get a node by ID."""
        with self._lock:
            node = self._nodes.get(node_id)
            return node.model_copy() if node else None

    def update_node_status(
        self,
        node_id: str,
        status: PlanStatus,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        output_payload: Optional[Any] = None,
    ) -> None:
        """Update node status and metadata in place."""
        with self._lock:
            if node_id not in self._nodes:
                return
            node = self._nodes[node_id]
            node.status = status
            if result is not None:
                node.result = result
            if error is not None:
                node.error = error
            if duration_ms > 0.0:
                node.duration_ms = duration_ms
            if output_payload is not None:
                node.output_payload = output_payload
            self._nodes[node_id] = node

    def increment_retry(self, node_id: str) -> int:
        """Increment retry count for node and return new retry count."""
        with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].retry_count += 1
                return self._nodes[node_id].retry_count
            return 0

    def has_cycle(self) -> bool:
        """Check if the graph contains any cycle using DFS."""
        with self._lock:
            visited: Set[str] = set()
            rec_stack: Set[str] = set()

            def _dfs(node_id: str) -> bool:
                visited.add(node_id)
                rec_stack.add(node_id)
                for neighbor in self._adjacency[node_id]:
                    if neighbor not in visited:
                        if _dfs(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True
                rec_stack.remove(node_id)
                return False

            for n_id in self._nodes:
                if n_id not in visited:
                    if _dfs(n_id):
                        return True
            return False

    def topological_sort(self) -> List[str]:
        """
        Return nodes in topological order using Kahn's algorithm.

        Raises:
            ValidationError: If cycle is detected.
        """
        with self._lock:
            in_degree = {n_id: len(self._reverse_adj[n_id]) for n_id in self._nodes}
            queue = deque([n_id for n_id, deg in in_degree.items() if deg == 0])
            sorted_order: List[str] = []

            while queue:
                curr = queue.popleft()
                sorted_order.append(curr)
                for neighbor in self._adjacency[curr]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            if len(sorted_order) != len(self._nodes):
                raise ValidationError("Graph contains cycles; topological sort is not possible.")

            return sorted_order

    def get_execution_levels(self) -> List[List[str]]:
        """
        Group nodes into parallel execution levels (layers) where all nodes in a layer
        can execute concurrently once previous layers complete.
        """
        with self._lock:
            in_degree = {n_id: len(self._reverse_adj[n_id]) for n_id in self._nodes}
            curr_layer = [n_id for n_id, deg in in_degree.items() if deg == 0]
            layers: List[List[str]] = []

            while curr_layer:
                layers.append(sorted(curr_layer))
                next_layer: List[str] = []
                for node_id in curr_layer:
                    for neighbor in self._adjacency[node_id]:
                        in_degree[neighbor] -= 1
                        if in_degree[neighbor] == 0:
                            next_layer.append(neighbor)
                curr_layer = next_layer

            return layers

    def propagate_failure(self, failed_node_id: str) -> List[str]:
        """
        Mark all downstream dependent nodes of a mandatory failed node as SKIPPED/CANCELLED.

        Returns:
            List of node IDs that were skipped due to failure propagation.
        """
        with self._lock:
            skipped: List[str] = []
            queue = deque(self._adjacency[failed_node_id])

            while queue:
                curr = queue.popleft()
                if curr in self._nodes and self._nodes[curr].status in (PlanStatus.PENDING, PlanStatus.RUNNING):
                    self._nodes[curr].status = PlanStatus.SKIPPED
                    self._nodes[curr].error = f"Skipped due to upstream failure in '{failed_node_id}'"
                    skipped.append(curr)
                    queue.extend(self._adjacency[curr])

            logger.warning(f"Failure in node '{failed_node_id}' propagated to skip {len(skipped)} downstream nodes.")
            return skipped

    def get_visualization_metadata(self) -> Dict[str, Any]:
        """Export dictionary metadata suitable for UI or DAG graph visualization."""
        with self._lock:
            return {
                "graph_id": self.graph_id,
                "request_id": self.request_id,
                "node_count": len(self._nodes),
                "edge_count": len(self._edges),
                "nodes": [
                    {
                        "id": n.node_id,
                        "label": n.agent_name,
                        "status": n.status.value,
                        "duration_ms": n.duration_ms,
                        "retry_count": n.retry_count,
                        "mandatory": n.mandatory,
                    }
                    for n in self._nodes.values()
                ],
                "edges": [
                    {
                        "source": e.source_node,
                        "target": e.target_node,
                        "type": e.dependency_type.value,
                    }
                    for e in self._edges
                ],
                "execution_levels": self.get_execution_levels(),
            }

    def to_model(self) -> ExecutionGraphModel:
        """Convert to serializable ExecutionGraphModel."""
        with self._lock:
            return ExecutionGraphModel(
                graph_id=self.graph_id,
                request_id=self.request_id,
                nodes={k: v.model_copy() for k, v in self._nodes.items()},
                edges=[e.model_copy() for e in self._edges],
                metadata=self.get_visualization_metadata(),
            )
