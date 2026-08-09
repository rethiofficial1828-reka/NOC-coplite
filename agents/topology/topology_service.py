"""
Topology Service Module.

Business logic layer that converts raw graph data from TopologyRepository
into strongly-typed TopologyAnalysis domain models.  This layer is the
single integration point for the TopologyAgent and for any future consumer
that needs network graph intelligence.

The service is stateless (all state lives in the repository) and thread-safe.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.topology.topology_graph import TopologyGraph
from agents.topology.topology_models import (
    BlastRadius,
    ImpactSeverity,
    ServiceImpact,
    TopologyAnalysis,
    TopologyDependency,
    TopologyLink,
    TopologyNode,
    TopologyPath,
    TopologyStatistics,
)
from agents.topology.topology_repository import TopologyRepository
from agents.topology.topology_validator import TopologyValidator

logger = get_agent_logger("TopologyService")


class TopologyService:
    """
    Business-logic service for topology graph analysis.

    Orchestrates calls to the repository, graph engine, and validator to
    produce TopologyAnalysis results consumed by the TopologyAgent.

    Args:
        repository: TopologyRepository instance.
        validator: TopologyValidator instance.
    """

    def __init__(
        self,
        repository: Optional[TopologyRepository] = None,
        validator: Optional[TopologyValidator] = None,
    ) -> None:
        self._repository = repository or TopologyRepository()
        self._validator = validator or TopologyValidator()
        self._lock = threading.RLock()

    @property
    def repository(self) -> TopologyRepository:
        """Repository instance used by this service."""
        return self._repository

    # ------------------------------------------------------------------
    # Primary analysis methods
    # ------------------------------------------------------------------

    def analyze_device(
        self,
        device_id: str,
        interface: str = "",
        incident_metadata: Optional[Dict[str, Any]] = None,
    ) -> TopologyAnalysis:
        """
        Produce a full TopologyAnalysis for a specific device.

        Steps:
            1. Load (or retrieve cached) graph.
            2. Validate topology structure.
            3. Locate device node (by ID or by name).
            4. Compute blast radius, upstream, downstream, shortest paths,
               dependency tree, redundant links, service impact.
            5. Assemble and return TopologyAnalysis.

        Args:
            device_id: Device identifier (node_id or human-readable name).
            interface: Optional interface name that triggered the analysis.
            incident_metadata: Optional additional metadata from the incident.

        Returns:
            TopologyAnalysis domain model.
        """
        with self._lock:
            graph = self._repository.get_graph()
            all_nodes = self._repository.get_all_nodes()
            all_links = self._repository.get_all_links()

            try:
                self._validator.validate(all_nodes, all_links)
            except Exception as exc:
                logger.warning(
                    "Topology validation warning during analyze_device: %s", exc
                )

            # Resolve node (supports both node_id and name lookup)
            node = graph.get_node(device_id)
            if node is None:
                node = self._repository.find_node_by_name(device_id)
            if node is None:
                logger.warning(
                    "Device '%s' not found in topology; returning partial analysis.",
                    device_id,
                )
                return self._empty_analysis(device_id, interface, incident_metadata)

            resolved_id = node.node_id

            # Graph computations
            blast_radius = graph.calculate_blast_radius(resolved_id)
            upstream_ids = graph.get_upstream(resolved_id)
            downstream_ids = graph.get_downstream(resolved_id)
            dependency_tree = graph.calculate_dependency_tree(resolved_id)
            service_impacts = graph.calculate_service_impact(resolved_id)

            # Shortest paths to all critical nodes (role-based selection)
            shortest_paths = self._compute_critical_paths(graph, resolved_id)

            # Redundant links on edges incident to this node
            redundant_links = self._find_redundant_links_for_node(
                graph, all_links, resolved_id
            )

            # Routing summary
            routing_summary = self._build_routing_summary(
                node, blast_radius, upstream_ids, downstream_ids, shortest_paths
            )

            overall_severity = self._aggregate_severity(blast_radius, service_impacts)

            metadata: Dict[str, Any] = {
                "node_name": node.name,
                "node_role": node.role.value,
                "node_location": node.location,
                "criticality": node.criticality,
            }
            if incident_metadata:
                metadata.update(incident_metadata)

            return TopologyAnalysis(
                device_id=resolved_id,
                interface=interface,
                impacted_devices=blast_radius.directly_affected_node_ids
                + blast_radius.transitively_affected_node_ids,
                impacted_services=service_impacts,
                blast_radius=blast_radius,
                upstream_devices=upstream_ids,
                downstream_devices=downstream_ids,
                shortest_paths=shortest_paths,
                dependency_tree=dependency_tree,
                redundant_links=redundant_links,
                routing_summary=routing_summary,
                overall_severity=overall_severity,
                timestamp=datetime.now(timezone.utc),
                metadata=metadata,
            )

    def analyze_incident(
        self,
        incident_payload: Dict[str, Any],
    ) -> TopologyAnalysis:
        """
        Produce a TopologyAnalysis derived from an incident payload dictionary.

        Extracts device_id and interface from standard incident fields
        (affected_entities, details) and delegates to analyze_device.

        Args:
            incident_payload: Incident dictionary containing at minimum
                              'affected_entities' or 'device_id'.

        Returns:
            TopologyAnalysis domain model.
        """
        device_id = self._extract_device_id(incident_payload)
        interface = self._extract_interface(incident_payload)
        return self.analyze_device(
            device_id=device_id,
            interface=interface,
            incident_metadata={
                "incident_id": str(incident_payload.get("incident_id", "")),
                "severity": str(incident_payload.get("severity", "")),
                "title": str(incident_payload.get("title", "")),
            },
        )

    def analyze_entire_network(self) -> List[TopologyAnalysis]:
        """
        Run analyze_device for every node in the topology graph.

        Returns:
            List of TopologyAnalysis objects, one per node.
        """
        analyses: List[TopologyAnalysis] = []
        for node in self._repository.get_all_nodes():
            try:
                analysis = self.analyze_device(node.node_id)
                analyses.append(analysis)
            except Exception as exc:
                logger.error(
                    "Failed to analyze node '%s': %s",
                    node.node_id,
                    exc,
                    exc_info=True,
                )
        return analyses

    # ------------------------------------------------------------------
    # Focused query methods
    # ------------------------------------------------------------------

    def find_affected_devices(self, device_id: str) -> List[str]:
        """
        Return all device IDs that would be impacted if *device_id* fails.

        Args:
            device_id: Failing device node ID.

        Returns:
            Sorted list of affected device IDs.
        """
        graph = self._repository.get_graph()
        br = graph.calculate_blast_radius(device_id)
        return sorted(
            set(br.directly_affected_node_ids + br.transitively_affected_node_ids)
        )

    def find_upstream_dependencies(self, device_id: str) -> List[TopologyNode]:
        """
        Return the TopologyNode objects that *device_id* depends on.

        Args:
            device_id: Target device node ID.

        Returns:
            List of upstream TopologyNode objects.
        """
        graph = self._repository.get_graph()
        upstream_ids = graph.get_upstream(device_id)
        result: List[TopologyNode] = []
        for uid in upstream_ids:
            node = graph.get_node(uid)
            if node:
                result.append(node)
        return result

    def find_downstream_dependencies(self, device_id: str) -> List[TopologyNode]:
        """
        Return the TopologyNode objects that depend on *device_id*.

        Args:
            device_id: Provider device node ID.

        Returns:
            List of downstream TopologyNode objects.
        """
        graph = self._repository.get_graph()
        downstream_ids = graph.get_downstream(device_id)
        result: List[TopologyNode] = []
        for did in downstream_ids:
            node = graph.get_node(did)
            if node:
                result.append(node)
        return result

    def calculate_blast_radius(self, device_id: str) -> BlastRadius:
        """
        Compute the blast radius for a single device failure.

        Args:
            device_id: Failing device node ID.

        Returns:
            BlastRadius domain model.
        """
        graph = self._repository.get_graph()
        return graph.calculate_blast_radius(device_id)

    def summarize_network_state(self) -> Dict[str, Any]:
        """
        Return a high-level dictionary summarising the current network state.

        Includes topology statistics and a list of all SPOF node IDs.

        Returns:
            Dictionary with keys: statistics, spof_nodes, total_services.
        """
        stats = self._repository.get_statistics()
        graph = self._repository.get_graph()
        spofs = graph.find_single_points_of_failure()

        return {
            "total_nodes": stats.total_nodes,
            "total_links": stats.total_links,
            "total_services": stats.total_services,
            "active_nodes": stats.active_nodes,
            "isolated_nodes": stats.isolated_nodes,
            "single_points_of_failure": spofs,
            "average_node_degree": stats.average_node_degree,
            "topology_source": stats.topology_source,
        }

    def get_statistics(self) -> TopologyStatistics:
        """
        Return aggregated topology statistics from the repository.

        Returns:
            TopologyStatistics domain model.
        """
        return self._repository.get_statistics()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_critical_paths(
        self, graph: TopologyGraph, source_id: str
    ) -> List[TopologyPath]:
        """
        Compute shortest paths from *source_id* to each critical node
        (those with criticality >= 7).

        Args:
            graph: Loaded TopologyGraph.
            source_id: Origin node ID.

        Returns:
            List of TopologyPath objects (one per reachable critical node).
        """
        paths: List[TopologyPath] = []
        for node in graph.get_all_nodes():
            if node.node_id == source_id:
                continue
            if node.criticality >= 7:
                path = graph.find_shortest_path(source_id, node.node_id)
                if path:
                    paths.append(path)
        return paths

    @staticmethod
    def _find_redundant_links_for_node(
        graph: TopologyGraph,
        all_links: List[TopologyLink],
        node_id: str,
    ) -> List[TopologyLink]:
        """
        Identify links incident on *node_id* where a parallel alternative exists.

        A link is considered redundant if there is at least one other link
        between the same pair of nodes.

        Args:
            graph: Loaded TopologyGraph.
            all_links: Full link list from the repository.
            node_id: Node to inspect.

        Returns:
            List of redundant TopologyLink objects.
        """
        incident: List[TopologyLink] = [
            lnk
            for lnk in all_links
            if lnk.source_node_id == node_id or lnk.target_node_id == node_id
        ]

        # Count edges per (src, dst) unordered pair
        from collections import Counter

        pair_count: Counter = Counter()
        for lnk in incident:
            pair = tuple(sorted([lnk.source_node_id, lnk.target_node_id]))
            pair_count[pair] += 1

        redundant: List[TopologyLink] = [
            lnk
            for lnk in incident
            if pair_count[
                tuple(sorted([lnk.source_node_id, lnk.target_node_id]))
            ]
            > 1
        ]

        # Mark redundant flag on link models
        redundant_ids = {lnk.link_id for lnk in redundant}
        for lnk in all_links:
            if lnk.link_id in redundant_ids:
                lnk.is_redundant = True

        return redundant

    @staticmethod
    def _build_routing_summary(
        node: TopologyNode,
        blast_radius: BlastRadius,
        upstream_ids: List[str],
        downstream_ids: List[str],
        paths: List[TopologyPath],
    ) -> str:
        """
        Compose a human-readable routing summary for the analysis artefact.

        Args:
            node: The node under analysis.
            blast_radius: Computed blast-radius result.
            upstream_ids: List of upstream node IDs.
            downstream_ids: List of downstream node IDs.
            paths: Computed critical shortest paths.

        Returns:
            Multi-line routing summary string.
        """
        lines: List[str] = [
            f"Device: {node.name} [{node.role.value}] — Location: {node.location or 'Unknown'}",
            f"Upstream providers: {len(upstream_ids)} node(s)",
            f"Downstream dependants: {len(downstream_ids)} node(s)",
            f"Blast radius: {blast_radius.total_affected_nodes} node(s) affected"
            f" ({blast_radius.impact_percentage:.1f}% of network)",
            f"Severity: {blast_radius.severity.value}",
        ]
        if blast_radius.single_points_of_failure:
            lines.append(
                f"SPOFs exposed: {', '.join(blast_radius.single_points_of_failure)}"
            )
        if paths:
            path_summary = "; ".join(
                f"{p.source_node_id}→{p.target_node_id} ({p.hop_count} hop(s))"
                for p in paths[:3]
            )
            lines.append(f"Critical paths: {path_summary}")
        return "\n".join(lines)

    @staticmethod
    def _aggregate_severity(
        blast_radius: BlastRadius,
        service_impacts: List[ServiceImpact],
    ) -> ImpactSeverity:
        """
        Derive the overall analysis severity from blast-radius and service impacts.

        Returns the highest severity across all computed dimensions.

        Args:
            blast_radius: Computed blast-radius result.
            service_impacts: List of ServiceImpact objects.

        Returns:
            Highest ImpactSeverity value found.
        """
        severity_order = [
            ImpactSeverity.NONE,
            ImpactSeverity.LOW,
            ImpactSeverity.MEDIUM,
            ImpactSeverity.HIGH,
            ImpactSeverity.CRITICAL,
        ]
        current = blast_radius.severity
        current_rank = severity_order.index(current)

        for impact in service_impacts:
            rank = severity_order.index(impact.severity)
            if rank > current_rank:
                current = impact.severity
                current_rank = rank

        return current

    @staticmethod
    def _extract_device_id(incident: Dict[str, Any]) -> str:
        """Extract the primary device ID from an incident dictionary."""
        # Prefer explicit device_id field
        if incident.get("device_id"):
            return str(incident["device_id"])
        # Fall back to first entry in affected_entities
        affected: List[Any] = incident.get("affected_entities", [])
        if affected:
            return str(affected[0])
        # Fall back to details sub-field
        details: Dict[str, Any] = incident.get("details", {})
        if details.get("device_id"):
            return str(details["device_id"])
        return "unknown"

    @staticmethod
    def _extract_interface(incident: Dict[str, Any]) -> str:
        """Extract the triggering interface name from an incident dictionary."""
        details: Dict[str, Any] = incident.get("details", {})
        return str(details.get("interface", incident.get("interface", "")))

    @staticmethod
    def _empty_analysis(
        device_id: str,
        interface: str,
        metadata: Optional[Dict[str, Any]],
    ) -> TopologyAnalysis:
        """
        Return a minimal TopologyAnalysis when the device is not found in topology.

        Args:
            device_id: The requested but unresolved device ID.
            interface: Interface name.
            metadata: Optional additional metadata.

        Returns:
            TopologyAnalysis with no graph data populated.
        """
        return TopologyAnalysis(
            device_id=device_id,
            interface=interface,
            routing_summary=f"Device '{device_id}' not found in topology graph.",
            overall_severity=ImpactSeverity.NONE,
            timestamp=datetime.now(timezone.utc),
            metadata=metadata or {},
        )
