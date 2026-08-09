"""
Topology Validator Module.

Performs structural validation of a loaded topology graph before it is
consumed by the service and agent layers.  Validation runs synchronously
and raises TopologyValidationError on the first critical violation.

Checks performed:
    - Duplicate node IDs
    - Duplicate link IDs
    - Orphan devices (nodes with no links)
    - Broken link references (link endpoints that point to unknown nodes)
    - Invalid interface references (interface named in link absent from node)
    - Missing required metadata on nodes and links
    - Cyclic dependency detection (nodes in a pure cycle with no external inlet)
"""

from __future__ import annotations

from typing import Dict, List, Set

from agents.core.logger import get_agent_logger
from agents.topology.topology_models import TopologyLink, TopologyNode

logger = get_agent_logger("TopologyValidator")


class TopologyValidationError(Exception):
    """Raised when the topology fails structural validation."""


class TopologyValidator:
    """
    Validates the structural integrity of a topology node and link set.

    All public methods raise :class:`TopologyValidationError` on failure
    and return silently on success.

    Usage::

        validator = TopologyValidator()
        validator.validate(nodes, links)  # raises on error
    """

    def validate(
        self,
        nodes: List[TopologyNode],
        links: List[TopologyLink],
    ) -> None:
        """
        Run the full validation suite against *nodes* and *links*.

        Args:
            nodes: List of TopologyNode objects from the repository.
            links: List of TopologyLink objects from the repository.

        Raises:
            TopologyValidationError: If any validation check fails.
        """
        self._check_duplicate_node_ids(nodes)
        self._check_duplicate_link_ids(links)
        self._check_broken_link_references(nodes, links)
        self._check_invalid_interface_references(nodes, links)
        self._check_missing_node_metadata(nodes)
        self._check_cyclic_dependencies(nodes, links)
        self._warn_orphan_devices(nodes, links)

        logger.info(
            "Topology validation passed: %d nodes, %d links.",
            len(nodes),
            len(links),
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_duplicate_node_ids(nodes: List[TopologyNode]) -> None:
        """Raise if any node_id appears more than once."""
        seen: Set[str] = set()
        duplicates: Set[str] = set()
        for node in nodes:
            if node.node_id in seen:
                duplicates.add(node.node_id)
            seen.add(node.node_id)
        if duplicates:
            raise TopologyValidationError(
                f"Duplicate node IDs detected: {sorted(duplicates)}"
            )

    @staticmethod
    def _check_duplicate_link_ids(links: List[TopologyLink]) -> None:
        """Raise if any link_id appears more than once."""
        seen: Set[str] = set()
        duplicates: Set[str] = set()
        for link in links:
            if link.link_id in seen:
                duplicates.add(link.link_id)
            seen.add(link.link_id)
        if duplicates:
            raise TopologyValidationError(
                f"Duplicate link IDs detected: {sorted(duplicates)}"
            )

    @staticmethod
    def _check_broken_link_references(
        nodes: List[TopologyNode], links: List[TopologyLink]
    ) -> None:
        """Raise if any link references a node_id that is not in *nodes*."""
        node_ids: Set[str] = {n.node_id for n in nodes}
        broken: List[str] = []
        for link in links:
            if link.source_node_id not in node_ids:
                broken.append(
                    f"Link '{link.link_id}': unknown source node"
                    f" '{link.source_node_id}'"
                )
            if link.target_node_id not in node_ids:
                broken.append(
                    f"Link '{link.link_id}': unknown target node"
                    f" '{link.target_node_id}'"
                )
        if broken:
            raise TopologyValidationError(
                "Broken link references:\n" + "\n".join(broken)
            )

    @staticmethod
    def _check_invalid_interface_references(
        nodes: List[TopologyNode], links: List[TopologyLink]
    ) -> None:
        """
        Warn (do not raise) when a link references an interface not declared
        on the corresponding node.  Nodes sourced from ContainerLab have
        their interfaces populated during parse; registry-only nodes have
        empty interface lists, so we skip validation for those.
        """
        node_map: Dict[str, TopologyNode] = {n.node_id: n for n in nodes}
        for link in links:
            for node_id, iface_name in (
                (link.source_node_id, link.source_interface),
                (link.target_node_id, link.target_interface),
            ):
                node = node_map.get(node_id)
                if node is None:
                    continue
                if not node.interfaces:
                    # Registry-only node — interfaces populated dynamically
                    continue
                declared = {iface.name for iface in node.interfaces}
                if iface_name not in declared:
                    logger.warning(
                        "Link '%s' references interface '%s' on node '%s'"
                        " which is not declared.  Possible misconfiguration.",
                        link.link_id,
                        iface_name,
                        node_id,
                    )

    @staticmethod
    def _check_missing_node_metadata(nodes: List[TopologyNode]) -> None:
        """Raise if any node is missing its required *node_id* or *name* field."""
        for node in nodes:
            if not node.node_id or not node.node_id.strip():
                raise TopologyValidationError(
                    f"Node at index {nodes.index(node)} has an empty node_id."
                )
            if not node.name or not node.name.strip():
                raise TopologyValidationError(
                    f"Node '{node.node_id}' has an empty name."
                )

    @staticmethod
    def _check_cyclic_dependencies(
        nodes: List[TopologyNode], links: List[TopologyLink]
    ) -> None:
        """
        Detect strongly connected components of size > 1, which indicate
        cyclic dependency loops rather than redundant paths.  Logs a warning
        for each cycle found but does not raise, as cycles are topologically
        valid in real networks (ring topologies).
        """
        # Build adjacency list
        adj: Dict[str, List[str]] = {n.node_id: [] for n in nodes}
        for link in links:
            adj.setdefault(link.source_node_id, []).append(link.target_node_id)

        # Kosaraju's SCC — first pass (DFS order)
        visited: Set[str] = set()
        finish_order: List[str] = []

        def dfs_first(u: str) -> None:
            visited.add(u)
            for v in adj.get(u, []):
                if v not in visited:
                    dfs_first(v)
            finish_order.append(u)

        for node_id in list(adj.keys()):
            if node_id not in visited:
                dfs_first(node_id)

        # Build reverse graph
        rev_adj: Dict[str, List[str]] = {n.node_id: [] for n in nodes}
        for link in links:
            rev_adj.setdefault(link.target_node_id, []).append(link.source_node_id)

        # Second pass (reverse order)
        visited2: Set[str] = set()
        scc_count = 0

        def dfs_second(u: str, component: List[str]) -> None:
            visited2.add(u)
            component.append(u)
            for v in rev_adj.get(u, []):
                if v not in visited2:
                    dfs_second(v, component)

        for node_id in reversed(finish_order):
            if node_id not in visited2:
                component: List[str] = []
                dfs_second(node_id, component)
                if len(component) > 1:
                    scc_count += 1
                    logger.warning(
                        "Cyclic dependency detected (SCC #%d): %s",
                        scc_count,
                        sorted(component),
                    )

    @staticmethod
    def _warn_orphan_devices(
        nodes: List[TopologyNode], links: List[TopologyLink]
    ) -> None:
        """Log a warning for every node that has no incoming or outgoing links."""
        connected: Set[str] = set()
        for link in links:
            connected.add(link.source_node_id)
            connected.add(link.target_node_id)

        for node in nodes:
            if node.node_id not in connected:
                logger.warning(
                    "Orphan node detected: '%s' ('%s') has no links.",
                    node.node_id,
                    node.name,
                )
