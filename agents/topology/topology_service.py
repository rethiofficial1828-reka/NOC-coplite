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
    TopologyIncidentImpact,
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

    def get_incident_topology_impact(
        self,
        target_device_or_interface: str,
        path_decision_service: Optional[Any] = None,
    ) -> TopologyIncidentImpact:
        """
        Produce a strongly-typed, read-only TopologyIncidentImpact assessment for operator investigation.

        Reuses existing domain services:
        - analyze_device() for graph traversal, BFS blast-radius, upstream/downstream dependencies, and SPOFs.
        - PathDiscoveryEngine / PathDecisionService for candidate alternative paths and recommendations.

        Args:
            target_device_or_interface: Name, ID, or interface under investigation (e.g. 'Branch3-Uplink').
            path_decision_service: Optional PathDecisionService instance to supply path candidates & recommendation.

        Returns:
            TopologyIncidentImpact read model with explicit provenance.
        """
        with self._lock:
            # 1. Handle empty / whitespace target safely
            if not target_device_or_interface or target_device_or_interface.strip() == "":
                return TopologyIncidentImpact(
                    target_entity="",
                    resolved_device_id="UNRESOLVED",
                    affected_interface="",
                    direct_dependencies=[],
                    affected_components=[],
                    dependent_links=[],
                    potential_service_impact=[],
                    single_points_of_failure=[],
                    blast_radius_level=ImpactSeverity.NONE,
                    impact_percentage=0.0,
                    alternative_paths=[],
                    recommendation="No target specified for topology impact assessment.",
                    evidence_sources=[
                        {
                            "source": "TopologyService",
                            "description": "Empty target entity provided; topology lookup skipped.",
                            "provenance": "INFERRED",
                        }
                    ],
                    provenance={
                        "target_entity": "OBSERVED",
                        "resolved_device_id": "INFERRED",
                        "blast_radius_level": "INFERRED",
                        "recommendation": "INFERRED",
                    },
                    metadata={"status": "EMPTY_TARGET"},
                )

            # 2. Run existing device topology analysis
            analysis = self.analyze_device(
                device_id=target_device_or_interface,
                interface=target_device_or_interface,
            )

            graph = self._repository.get_graph()
            all_links = self._repository.get_all_links()

            resolved_node = graph.get_node(analysis.device_id)
            if resolved_node is None:
                resolved_node = self._repository.find_node_by_name(target_device_or_interface)

            # 3. Handle non-existent device safely
            if resolved_node is None:
                return TopologyIncidentImpact(
                    target_entity=target_device_or_interface,
                    resolved_device_id="UNRESOLVED",
                    affected_interface=target_device_or_interface,
                    direct_dependencies=[],
                    affected_components=[],
                    dependent_links=[],
                    potential_service_impact=[],
                    single_points_of_failure=[],
                    blast_radius_level=ImpactSeverity.NONE,
                    impact_percentage=0.0,
                    alternative_paths=[],
                    recommendation=f"Target '{target_device_or_interface}' not found in active network topology registry.",
                    evidence_sources=[
                        {
                            "source": "TopologyRepository",
                            "description": f"Target entity '{target_device_or_interface}' not resolved in topology graph.",
                            "provenance": "OBSERVED",
                        }
                    ],
                    provenance={
                        "target_entity": "OBSERVED",
                        "resolved_device_id": "INFERRED",
                        "blast_radius_level": "INFERRED",
                        "recommendation": "INFERRED",
                    },
                    metadata={"status": "UNRESOLVED_TARGET"},
                )

            resolved_id = resolved_node.node_id
            affected_iface = analysis.interface or target_device_or_interface

            # 4. Direct dependencies & incident-affected links from actual links
            direct_deps: List[str] = []
            dependent_links: List[str] = []
            for lnk in all_links:
                if lnk.source_node_id == resolved_id:
                    direct_deps.append(lnk.target_node_id)
                    dependent_links.append(
                        f"{lnk.source_node_id}:{lnk.source_interface} -> {lnk.target_node_id}:{lnk.target_interface}"
                    )
                elif lnk.target_node_id == resolved_id:
                    direct_deps.append(lnk.source_node_id)
                    dependent_links.append(
                        f"{lnk.source_node_id}:{lnk.source_interface} -> {lnk.target_node_id}:{lnk.target_interface}"
                    )
            direct_dependencies = sorted(list(set(direct_deps)))

            # 5. Affected components (directly and transitively affected)
            affected_components = list(analysis.impacted_devices)

            # 6. Potential service impact
            service_impact_list: List[str] = []
            if analysis.impacted_services:
                for si in analysis.impacted_services:
                    service_impact_list.append(
                        f"{si.service_name} (Severity: {si.severity.value}, Loss: {'Total' if si.is_total_loss else 'Degraded'}, Alt Paths: {si.redundant_paths_available})"
                    )
            else:
                # Infer logical services from node role and connectivity
                if resolved_node.role.value in ("wan_interface", "edge", "router"):
                    service_impact_list.append("Branch WAN Egress (Primary Path Degradation)")
                    service_impact_list.append("Site-to-Site SD-WAN Tunnel (Subject to Jitter/Loss)")
                    service_impact_list.append("Egress Routing to Campus Core")
                elif resolved_node.role.value in ("core", "distribution"):
                    service_impact_list.append("Campus Backbone Routing")
                    service_impact_list.append("Enterprise Gateway Transit")
                elif resolved_node.role.value == "firewall":
                    service_impact_list.append("Edge Perimeter Security & NAT")
                    service_impact_list.append("VPN Tunnel Termination")

            # 7. Single points of failure & Blast radius
            spofs = (
                list(analysis.blast_radius.single_points_of_failure)
                if analysis.blast_radius
                else []
            )
            blast_level = (
                analysis.blast_radius.severity
                if analysis.blast_radius
                else ImpactSeverity.LOW
            )
            impact_pct = (
                analysis.blast_radius.impact_percentage
                if analysis.blast_radius
                else 0.0
            )

            # 8. Alternative paths & Recommendation from existing path discovery / decision engine
            alt_paths: List[str] = []
            rec_text = ""
            try:
                if path_decision_service is not None:
                    p_res = path_decision_service.evaluate_path_decision(target_device_or_interface)
                    if p_res and p_res.candidate_paths:
                        for c in p_res.candidate_paths:
                            if not c.is_primary:
                                alt_paths.append(
                                    f"{c.provider_name} via {c.wan_interface} (Bandwidth: {c.bandwidth_mbps:.0f} Mbps, Hops: {' -> '.join(c.hops)})"
                                )
                        if p_res.recommendation:
                            rec = p_res.recommendation
                            if rec.recommended_provider and rec.recommended_provider != rec.current_provider:
                                rec_text = f"Switch traffic from {rec.current_provider} ({rec.current_status}) to candidate {rec.recommended_provider} ({rec.decision_status.value})."
                            else:
                                rec_text = f"Maintain active provider {rec.current_provider} ({rec.decision_status.value})."
                else:
                    from agents.path_decision.path_discovery import PathDiscoveryEngine

                    disc = PathDiscoveryEngine(topology_service=self)
                    _primary, candidates, _status = disc.discover_paths(target_device_or_interface)
                    if candidates:
                        for c in candidates:
                            if not c.is_primary:
                                alt_paths.append(
                                    f"{c.provider_name} via {c.wan_interface} (Bandwidth: {c.bandwidth_mbps:.0f} Mbps, Hops: {' -> '.join(c.hops)})"
                                )
            except Exception as exc:
                logger.debug("Path decision evaluation skipped during topology impact: %s", exc)

            if not rec_text and alt_paths:
                rec_text = f"Consider alternate path: {alt_paths[0]} if degradation exceeds SLA thresholds."
            elif not rec_text:
                rec_text = "No alternative paths discovered in current topology graph."

            # 9. Assemble explicit evidence records & provenance
            evidence_sources: List[Dict[str, str]] = [
                {
                    "source": "topology.clab.yml / DEVICE_REGISTRY",
                    "description": f"Direct link connections to adjacent nodes: {', '.join(direct_dependencies)}",
                    "provenance": "OBSERVED",
                },
                {
                    "source": "TopologyGraph.calculate_blast_radius",
                    "description": f"Blast radius: {blast_level.value} ({impact_pct:.1f}% network impact, {len(affected_components)} components)",
                    "provenance": "INFERRED",
                },
                {
                    "source": "TopologyGraph.find_single_points_of_failure",
                    "description": f"SPOFs in subgraph: {', '.join(spofs) if spofs else 'None'}",
                    "provenance": "INFERRED",
                },
            ]
            if alt_paths:
                evidence_sources.append(
                    {
                        "source": "PathDiscoveryEngine",
                        "description": f"Discovered alternative paths: {', '.join(alt_paths)}",
                        "provenance": "OBSERVED",
                    }
                )
            if rec_text:
                evidence_sources.append(
                    {
                        "source": "PathDecisionService",
                        "description": f"Topology recommendation: {rec_text}",
                        "provenance": "SIMULATION",
                    }
                )

            provenance_map: Dict[str, str] = {
                "target_entity": "OBSERVED",
                "resolved_device_id": "OBSERVED",
                "affected_interface": "OBSERVED",
                "direct_dependencies": "OBSERVED",
                "dependent_links": "OBSERVED",
                "affected_components": "INFERRED",
                "single_points_of_failure": "INFERRED",
                "blast_radius_level": "INFERRED",
                "impact_percentage": "INFERRED",
                "potential_service_impact": "PREDICTED",
                "alternative_paths": "OBSERVED",
                "recommendation": "SIMULATION",
            }

            return TopologyIncidentImpact(
                target_entity=target_device_or_interface,
                resolved_device_id=resolved_id,
                affected_interface=affected_iface,
                direct_dependencies=direct_dependencies,
                affected_components=affected_components,
                dependent_links=dependent_links,
                potential_service_impact=service_impact_list,
                single_points_of_failure=spofs,
                blast_radius_level=blast_level,
                impact_percentage=round(impact_pct, 2),
                alternative_paths=alt_paths,
                recommendation=rec_text,
                evidence_sources=evidence_sources,
                provenance=provenance_map,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "node_name": resolved_node.name,
                    "node_role": resolved_node.role.value,
                    "criticality": resolved_node.criticality,
                },
            )

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
