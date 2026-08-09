"""
Topology Graph Engine Module.

Implements a pure-Python, adjacency-list-based directed graph engine.
No third-party graph libraries (e.g. NetworkX) are used.  All algorithms
are deterministic and thread-safe when called with an immutable snapshot
of topology data.

Algorithms provided:
    - Shortest path (Dijkstra's with min-heap)
    - Blast-radius (BFS from a failing node)
    - Dependency tree construction (DFS upstream / downstream)
    - Redundant path detection (BFS-based alternative enumeration)
    - Single-point-of-failure detection (articulation-point via DFS)
    - Service impact calculation
"""

from __future__ import annotations

import heapq
import threading
from collections import deque
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from agents.core.logger import get_agent_logger
from agents.topology.topology_models import (
    BlastRadius,
    ImpactSeverity,
    ServiceImpact,
    TopologyDependency,
    TopologyLink,
    TopologyNode,
    TopologyPath,
)

logger = get_agent_logger("TopologyGraph")

# Internal representation: adjacency list entry
# (weight, target_node_id, link_id)
_AdjEntry = Tuple[float, str, str]


class TopologyGraph:
    """
    Directed, weighted adjacency-list graph engine for topology analysis.

    The graph is built once from a set of TopologyNode and TopologyLink
    objects and then treated as immutable for read operations.  All public
    methods are thread-safe.

    Args:
        nodes: Sequence of TopologyNode domain objects.
        links: Sequence of TopologyLink domain objects.
    """

    def __init__(
        self,
        nodes: Optional[List[TopologyNode]] = None,
        links: Optional[List[TopologyLink]] = None,
    ) -> None:
        self._lock = threading.RLock()

        # Primary stores keyed by ID
        self._nodes: Dict[str, TopologyNode] = {}
        self._links: Dict[str, TopologyLink] = {}

        # Adjacency: node_id -> list of (weight, target_node_id, link_id)
        self._adj_out: Dict[str, List[_AdjEntry]] = {}
        # Reverse adjacency for upstream traversal
        self._adj_in: Dict[str, List[_AdjEntry]] = {}

        if nodes:
            for node in nodes:
                self._add_node(node)
        if links:
            for link in links:
                self._add_link(link)

    # ------------------------------------------------------------------
    # Graph construction helpers
    # ------------------------------------------------------------------

    def _add_node(self, node: TopologyNode) -> None:
        self._nodes[node.node_id] = node
        if node.node_id not in self._adj_out:
            self._adj_out[node.node_id] = []
        if node.node_id not in self._adj_in:
            self._adj_in[node.node_id] = []

    def _add_link(self, link: TopologyLink) -> None:
        self._links[link.link_id] = link
        # Ensure adjacency lists exist even if nodes were omitted
        for nid in (link.source_node_id, link.target_node_id):
            self._adj_out.setdefault(nid, [])
            self._adj_in.setdefault(nid, [])

        entry_out: _AdjEntry = (link.weight, link.target_node_id, link.link_id)
        entry_in: _AdjEntry = (link.weight, link.source_node_id, link.link_id)
        self._adj_out[link.source_node_id].append(entry_out)
        self._adj_in[link.target_node_id].append(entry_in)

    # ------------------------------------------------------------------
    # Node & neighbour access
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> Optional[TopologyNode]:
        """Return a TopologyNode by ID, or None if not found."""
        with self._lock:
            return self._nodes.get(node_id)

    def get_all_nodes(self) -> List[TopologyNode]:
        """Return all nodes in the graph."""
        with self._lock:
            return list(self._nodes.values())

    def get_all_links(self) -> List[TopologyLink]:
        """Return all links in the graph."""
        with self._lock:
            return list(self._links.values())

    def get_neighbors(self, node_id: str) -> List[TopologyNode]:
        """
        Return the direct outgoing neighbours of *node_id*.

        Args:
            node_id: Source node identifier.

        Returns:
            List of TopologyNode objects that are directly reachable.
        """
        with self._lock:
            result: List[TopologyNode] = []
            for _w, target_id, _lid in self._adj_out.get(node_id, []):
                node = self._nodes.get(target_id)
                if node is not None:
                    result.append(node)
            return result

    def get_upstream(self, node_id: str) -> List[str]:
        """
        Return all node IDs that have *node_id* as a downstream dependency.

        Performs a BFS over the reverse adjacency (incoming edges).

        Args:
            node_id: The device whose upstream providers are sought.

        Returns:
            Ordered list of node IDs reachable via incoming edges (BFS order).
        """
        with self._lock:
            visited: Set[str] = set()
            queue: deque[str] = deque([node_id])
            visited.add(node_id)
            result: List[str] = []

            while queue:
                current = queue.popleft()
                for _w, src_id, _lid in self._adj_in.get(current, []):
                    if src_id not in visited:
                        visited.add(src_id)
                        queue.append(src_id)
                        result.append(src_id)
            return result

    def get_downstream(self, node_id: str) -> List[str]:
        """
        Return all node IDs that transitively depend on *node_id*.

        Performs a BFS over the forward adjacency (outgoing edges).

        Args:
            node_id: The device whose downstream dependants are sought.

        Returns:
            Ordered list of node IDs reachable via outgoing edges (BFS order).
        """
        with self._lock:
            visited: Set[str] = set()
            queue: deque[str] = deque([node_id])
            visited.add(node_id)
            result: List[str] = []

            while queue:
                current = queue.popleft()
                for _w, tgt_id, _lid in self._adj_out.get(current, []):
                    if tgt_id not in visited:
                        visited.add(tgt_id)
                        queue.append(tgt_id)
                        result.append(tgt_id)
            return result

    # ------------------------------------------------------------------
    # Shortest path  (Dijkstra)
    # ------------------------------------------------------------------

    def find_shortest_path(
        self, source_id: str, target_id: str
    ) -> Optional[TopologyPath]:
        """
        Compute the shortest (minimum-weight) path between two nodes.

        Uses Dijkstra's algorithm with a binary min-heap.

        Args:
            source_id: Origin node ID.
            target_id: Destination node ID.

        Returns:
            TopologyPath if a path exists, otherwise None.
        """
        with self._lock:
            if source_id not in self._adj_out or target_id not in self._adj_out:
                return None
            if source_id == target_id:
                return TopologyPath(
                    source_node_id=source_id,
                    target_node_id=target_id,
                    hops=[source_id],
                    hop_count=0,
                    total_weight=0.0,
                    is_shortest=True,
                )

            # dist[node] = (cumulative_weight, predecessor_node)
            dist: Dict[str, float] = {source_id: 0.0}
            prev: Dict[str, Optional[str]] = {source_id: None}
            # heap: (weight, node_id)
            heap: List[Tuple[float, str]] = [(0.0, source_id)]

            while heap:
                cost, current = heapq.heappop(heap)
                if current == target_id:
                    break
                if cost > dist.get(current, float("inf")):
                    continue
                for w, neighbour, _lid in self._adj_out.get(current, []):
                    new_cost = cost + w
                    if new_cost < dist.get(neighbour, float("inf")):
                        dist[neighbour] = new_cost
                        prev[neighbour] = current
                        heapq.heappush(heap, (new_cost, neighbour))

            if target_id not in dist:
                return None  # No path found

            # Reconstruct path
            hops: List[str] = []
            node: Optional[str] = target_id
            while node is not None:
                hops.append(node)
                node = prev.get(node)
            hops.reverse()

            return TopologyPath(
                source_node_id=source_id,
                target_node_id=target_id,
                hops=hops,
                hop_count=len(hops) - 1,
                total_weight=dist[target_id],
                is_shortest=True,
            )

    # ------------------------------------------------------------------
    # Blast radius
    # ------------------------------------------------------------------

    def calculate_blast_radius(self, origin_node_id: str) -> BlastRadius:
        """
        Compute the blast radius for the failure of *origin_node_id*.

        The blast radius covers:
        - Directly affected neighbours (those reachable only through origin).
        - Transitively affected nodes (full downstream BFS after removing origin).
        - Affected services (union of services on all affected nodes).
        - SPOFs exposed by this failure.
        - Impact percentage relative to the total graph size.

        Args:
            origin_node_id: Node ID of the failing device.

        Returns:
            BlastRadius domain model.
        """
        with self._lock:
            total_nodes = len(self._nodes)

            # Downstream BFS from origin (all nodes that depended on origin)
            downstream = set(self.get_downstream(origin_node_id))

            # Determine which downstream nodes become isolated (cannot reach
            # any node outside the downstream set without going through origin)
            directly_affected: List[str] = []
            transitively_affected: List[str] = []

            for node_id in downstream:
                # A node is directly affected if origin was its only upstream
                incoming_sources = {
                    src for _w, src, _lid in self._adj_in.get(node_id, [])
                }
                # Remove origin from consideration
                alt_sources = incoming_sources - {origin_node_id}
                if not alt_sources or all(
                    s in downstream or s == origin_node_id for s in alt_sources
                ):
                    directly_affected.append(node_id)
                else:
                    transitively_affected.append(node_id)

            all_affected = list(downstream)

            # Collect impacted services
            affected_services: Set[str] = set()
            origin_node = self._nodes.get(origin_node_id)
            if origin_node:
                affected_services.update(origin_node.services)
            for nid in all_affected:
                node = self._nodes.get(nid)
                if node:
                    affected_services.update(node.services)

            # Identify SPOFs (nodes with degree 1 incoming in affected subgraph)
            spofs = self._find_spofs_in_set(
                {origin_node_id} | set(all_affected)
            )

            total_affected = len(all_affected)
            impact_pct = (
                (total_affected / total_nodes * 100.0) if total_nodes > 0 else 0.0
            )

            severity = self._classify_severity(impact_pct, len(spofs))

            return BlastRadius(
                origin_node_id=origin_node_id,
                directly_affected_node_ids=sorted(directly_affected),
                transitively_affected_node_ids=sorted(transitively_affected),
                affected_services=sorted(affected_services),
                single_points_of_failure=sorted(spofs),
                total_affected_nodes=total_affected,
                impact_percentage=round(impact_pct, 2),
                severity=severity,
                metadata={"origin_node_name": origin_node.name if origin_node else ""},
            )

    # ------------------------------------------------------------------
    # Dependency tree
    # ------------------------------------------------------------------

    def calculate_dependency_tree(
        self, node_id: str
    ) -> List[TopologyDependency]:
        """
        Build a directed dependency tree rooted at *node_id*.

        Traverses both upstream (providers) and downstream (dependants)
        using BFS and encodes each edge as a TopologyDependency.

        Args:
            node_id: Root node for dependency analysis.

        Returns:
            List of TopologyDependency objects.
        """
        with self._lock:
            dependencies: List[TopologyDependency] = []
            visited_edges: Set[FrozenSet[str]] = set()

            # Upstream dependencies (node_id depends on upstream)
            upstream_ids = self.get_upstream(node_id)
            for uid in upstream_ids:
                edge_key: FrozenSet[str] = frozenset([uid, node_id])
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                    # Is this a critical dependency? Check if there's only one
                    # upstream provider (i.e., no alternative for node_id -> uid)
                    providers = {
                        src for _w, src, _lid in self._adj_in.get(node_id, [])
                    }
                    is_critical = len(providers) <= 1
                    dependencies.append(
                        TopologyDependency(
                            dependent_node_id=node_id,
                            provider_node_id=uid,
                            dependency_type="upstream_network",
                            is_critical=is_critical,
                        )
                    )

            # Downstream dependencies (downstream nodes depend on node_id)
            downstream_ids = self.get_downstream(node_id)
            for did in downstream_ids:
                edge_key = frozenset([node_id, did])
                if edge_key not in visited_edges:
                    visited_edges.add(edge_key)
                    providers_of_downstream = {
                        src for _w, src, _lid in self._adj_in.get(did, [])
                    }
                    is_critical = len(providers_of_downstream) <= 1
                    dependencies.append(
                        TopologyDependency(
                            dependent_node_id=did,
                            provider_node_id=node_id,
                            dependency_type="downstream_network",
                            is_critical=is_critical,
                        )
                    )

            return dependencies

    # ------------------------------------------------------------------
    # Redundant path detection
    # ------------------------------------------------------------------

    def find_redundant_paths(
        self, source_id: str, target_id: str, max_paths: int = 5
    ) -> List[TopologyPath]:
        """
        Find up to *max_paths* node-disjoint paths between source and target.

        Uses repeated Dijkstra runs with previously used intermediate nodes
        blocked (Yen's k-shortest approximation, simplified for node-disjoint).

        Args:
            source_id: Origin node ID.
            target_id: Destination node ID.
            max_paths: Maximum number of distinct paths to return.

        Returns:
            List of TopologyPath objects sorted by total_weight.
        """
        with self._lock:
            paths: List[TopologyPath] = []
            blocked_nodes: Set[str] = set()

            for _ in range(max_paths):
                path = self._dijkstra_with_blocked(
                    source_id, target_id, blocked_nodes
                )
                if path is None:
                    break
                paths.append(path)
                # Block intermediate nodes to force a different route next time
                intermediates = path.hops[1:-1]
                blocked_nodes.update(intermediates)

            # Mark all as non-shortest (only the first is shortest)
            for i, p in enumerate(paths):
                p.is_shortest = i == 0

            return paths

    def _dijkstra_with_blocked(
        self, source_id: str, target_id: str, blocked: Set[str]
    ) -> Optional[TopologyPath]:
        """Internal Dijkstra that treats *blocked* nodes as non-traversable."""
        if source_id not in self._adj_out or target_id not in self._adj_out:
            return None

        dist: Dict[str, float] = {source_id: 0.0}
        prev: Dict[str, Optional[str]] = {source_id: None}
        heap: List[Tuple[float, str]] = [(0.0, source_id)]

        while heap:
            cost, current = heapq.heappop(heap)
            if current == target_id:
                break
            if cost > dist.get(current, float("inf")):
                continue
            for w, neighbour, _lid in self._adj_out.get(current, []):
                if neighbour in blocked and neighbour != target_id:
                    continue
                new_cost = cost + w
                if new_cost < dist.get(neighbour, float("inf")):
                    dist[neighbour] = new_cost
                    prev[neighbour] = current
                    heapq.heappush(heap, (new_cost, neighbour))

        if target_id not in dist:
            return None

        hops: List[str] = []
        node: Optional[str] = target_id
        while node is not None:
            hops.append(node)
            node = prev.get(node)
        hops.reverse()

        return TopologyPath(
            source_node_id=source_id,
            target_node_id=target_id,
            hops=hops,
            hop_count=len(hops) - 1,
            total_weight=dist[target_id],
            is_shortest=False,
        )

    # ------------------------------------------------------------------
    # SPOF detection (articulation points via Tarjan's bridge algorithm)
    # ------------------------------------------------------------------

    def find_single_points_of_failure(self) -> List[str]:
        """
        Identify all single points of failure (articulation points) in the graph.

        A node is an articulation point if its removal increases the number
        of weakly connected components.  Uses Tarjan's DFS-based algorithm.

        Returns:
            List of node IDs that are single points of failure.
        """
        with self._lock:
            return self._find_spofs_in_set(set(self._nodes.keys()))

    def _find_spofs_in_set(self, node_ids: Set[str]) -> List[str]:
        """
        Find articulation points among the subset of nodes in *node_ids*.

        Args:
            node_ids: Set of node IDs to consider as the subgraph.

        Returns:
            List of articulation-point node IDs within the subgraph.
        """
        visited: Dict[str, int] = {}
        low: Dict[str, int] = {}
        parent: Dict[str, Optional[str]] = {}
        articulation: Set[str] = set()
        timer = [0]

        def dfs(u: str) -> None:
            visited[u] = low[u] = timer[0]
            timer[0] += 1
            child_count = 0

            # Combine forward and reverse adjacency for undirected SPOF detection
            neighbours: Set[str] = set()
            for _w, v, _lid in self._adj_out.get(u, []):
                if v in node_ids:
                    neighbours.add(v)
            for _w, v, _lid in self._adj_in.get(u, []):
                if v in node_ids:
                    neighbours.add(v)

            for v in neighbours:
                if v not in visited:
                    child_count += 1
                    parent[v] = u
                    dfs(v)
                    low[u] = min(low[u], low[v])
                    # Root with 2+ children is an articulation point
                    if parent.get(u) is None and child_count > 1:
                        articulation.add(u)
                    # Non-root where low[v] >= disc[u]
                    if parent.get(u) is not None and low[v] >= visited[u]:
                        articulation.add(u)
                elif v != parent.get(u):
                    low[u] = min(low[u], visited[v])

        for node_id in node_ids:
            if node_id not in visited:
                parent[node_id] = None
                dfs(node_id)

        return sorted(articulation)

    # ------------------------------------------------------------------
    # Service impact
    # ------------------------------------------------------------------

    def calculate_service_impact(
        self, failing_node_id: str
    ) -> List[ServiceImpact]:
        """
        Assess the impact on all services caused by *failing_node_id* failing.

        For each service hosted anywhere in the graph, determines whether the
        failure severs all paths to that service, counts remaining redundant
        paths, and assigns a severity level.

        Args:
            failing_node_id: The node assumed to have failed.

        Returns:
            List of ServiceImpact objects for each discovered service.
        """
        with self._lock:
            # Gather all services and the nodes hosting them
            service_nodes: Dict[str, List[str]] = {}
            for node in self._nodes.values():
                for svc in node.services:
                    service_nodes.setdefault(svc, []).append(node.node_id)

            impacts: List[ServiceImpact] = []

            for svc_name, hosting_nodes in service_nodes.items():
                affected = [
                    nid
                    for nid in hosting_nodes
                    if nid == failing_node_id
                    or nid in set(self.get_downstream(failing_node_id))
                ]

                total_hosting = len(hosting_nodes)
                total_affected = len(affected)
                redundant_available = total_hosting - total_affected
                is_total_loss = redundant_available <= 0

                if is_total_loss:
                    severity = ImpactSeverity.CRITICAL
                    summary = f"Service '{svc_name}' has no remaining healthy nodes."
                elif redundant_available == 1:
                    severity = ImpactSeverity.HIGH
                    summary = (
                        f"Service '{svc_name}' has only 1 remaining node; "
                        "no redundancy."
                    )
                elif total_affected > 0:
                    severity = ImpactSeverity.MEDIUM
                    summary = (
                        f"Service '{svc_name}' degraded; {total_affected} node(s)"
                        " affected but {redundant_available} remain."
                    )
                else:
                    severity = ImpactSeverity.NONE
                    summary = f"Service '{svc_name}' is unaffected."

                impacts.append(
                    ServiceImpact(
                        service_name=svc_name,
                        affected_node_ids=affected,
                        severity=severity,
                        is_total_loss=is_total_loss,
                        redundant_paths_available=max(0, redundant_available),
                        estimated_user_impact=summary,
                    )
                )

            return impacts

    # ------------------------------------------------------------------
    # Graph statistics helpers
    # ------------------------------------------------------------------

    def node_count(self) -> int:
        """Return total number of nodes in the graph."""
        with self._lock:
            return len(self._nodes)

    def link_count(self) -> int:
        """Return total number of links in the graph."""
        with self._lock:
            return len(self._links)

    def is_connected(self, source_id: str, target_id: str) -> bool:
        """
        Return True if *target_id* is reachable from *source_id*.

        Args:
            source_id: Start node.
            target_id: End node.

        Returns:
            True if a directed path exists.
        """
        with self._lock:
            return self.find_shortest_path(source_id, target_id) is not None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_severity(
        impact_percentage: float, spof_count: int
    ) -> ImpactSeverity:
        """Derive impact severity from blast-radius percentage and SPOF count."""
        if impact_percentage >= 50.0 or spof_count >= 3:
            return ImpactSeverity.CRITICAL
        if impact_percentage >= 25.0 or spof_count >= 2:
            return ImpactSeverity.HIGH
        if impact_percentage >= 10.0 or spof_count >= 1:
            return ImpactSeverity.MEDIUM
        if impact_percentage > 0.0:
            return ImpactSeverity.LOW
        return ImpactSeverity.NONE
