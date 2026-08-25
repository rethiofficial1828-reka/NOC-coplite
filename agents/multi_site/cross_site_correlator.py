"""
Cross-Site Incident Correlation Service Module for NOC-Copilot v1.3.

Provides deterministic, evidence-grounded multi-site incident correlation across:
1. SHARED_PROVIDER (Multiple distinct sites experiencing degraded upstream provider)
2. SHARED_TOPOLOGY_DEPENDENCY (Multiple sites impacted by common upstream transit choke point)
3. SIMILAR_FAILURE_SIGNATURE (Deterministic fingerprint and pattern match)
4. SYNCHRONIZED_TEMPORAL (Coincident anomalies occurring within <= 60 seconds)

Strictly read-only and advisory. Does not fabricate evidence or mutate state.
"""

from datetime import datetime, timezone
import math
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from agents.core.logger import get_agent_logger
from agents.incident.incident_models import IncidentRecord, IncidentStatus
from agents.incident.incident_service import IncidentService
from agents.multi_site.multi_site_models import (
    CorrelatedIncidentGroup,
    CorrelationType,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.orchestrator_ai.evidence_registry import EvidenceRegistry
from agents.premortem.incident_fingerprint import IncidentFingerprintEngine
from agents.topology.topology_service import TopologyService

logger = get_agent_logger("CrossSiteCorrelationService")


class CrossSiteCorrelationService:
    """
    Deterministic, evidence-grounded cross-site incident correlation service.
    Analyzes active incidents across physical/logical sites to discover common root causes.
    """

    def __init__(
        self,
        inventory_service: Optional[MultiSiteInventoryService] = None,
        incident_service: Optional[IncidentService] = None,
        topology_service: Optional[TopologyService] = None,
        fingerprint_engine: Optional[IncidentFingerprintEngine] = None,
        evidence_registry: Optional[EvidenceRegistry] = None,
    ) -> None:
        self._inventory_service = inventory_service or MultiSiteInventoryService()
        self._incident_service = incident_service or IncidentService()
        self._topology_service = topology_service or TopologyService()
        self._fingerprint_engine = fingerprint_engine or IncidentFingerprintEngine()
        self._evidence_registry = evidence_registry or EvidenceRegistry()
        self._lock = threading.RLock()

    def correlate_active_incidents(
        self, incidents: Optional[List[IncidentRecord]] = None
    ) -> List[CorrelatedIncidentGroup]:
        """
        Scan active incidents across all sites and produce deduplicated CorrelatedIncidentGroups.

        Args:
            incidents: Optional explicit list of IncidentRecords. If None, queries active incidents.

        Returns:
            List of deduplicated CorrelatedIncidentGroup objects.
        """
        with self._lock:
            # 1. Fetch active incidents if not provided
            if incidents is None:
                all_incs = self._incident_service.get_all_incidents()
                active_statuses = (
                    IncidentStatus.NEW,
                    IncidentStatus.OPEN,
                    IncidentStatus.ACKNOWLEDGED,
                    IncidentStatus.IN_PROGRESS,
                )
                target_incidents = [i for i in all_incs if i.status in active_statuses]
            else:
                target_incidents = list(incidents)

            if len(target_incidents) < 2:
                # Correlation requires at least 2 incidents
                return []

            # 2. Extract correlation candidates across all 4 dimensions
            raw_groups: List[CorrelatedIncidentGroup] = []

            # Dimension 1: Shared Provider
            raw_groups.extend(self._correlate_shared_provider(target_incidents))

            # Dimension 2: Shared Topology Dependency
            raw_groups.extend(self._correlate_shared_topology(target_incidents))

            # Dimension 3: Similar Failure Signature
            raw_groups.extend(self._correlate_similar_signature(target_incidents))

            # Dimension 4: Synchronized Temporal Anomaly
            raw_groups.extend(self._correlate_synchronized_temporal(target_incidents))

            # 3. Deduplicate and merge overlapping candidate groups
            merged_groups = self._deduplicate_and_merge(raw_groups)
            return merged_groups

    # -----------------------------------------------------------------------
    # Dimension 1: Shared Provider
    # -----------------------------------------------------------------------
    def _correlate_shared_provider(
        self, incidents: List[IncidentRecord]
    ) -> List[CorrelatedIncidentGroup]:
        """Correlate incidents spanning multiple sites that share a degraded upstream provider."""
        provider_map: Dict[str, List[Tuple[IncidentRecord, str]]] = {}

        for inc in incidents:
            site = self._inventory_service.get_site_for_device(inc.device_id) or self._inventory_service.get_site_for_device(inc.interface)
            site_id = site.site_id if site else "site-unknown"

            # Identify provider from incident metadata, signals, title, or site configuration
            detected_providers = self._extract_providers_for_incident(inc, site)
            for p in detected_providers:
                if p not in provider_map:
                    provider_map[p] = []
                provider_map[p].append((inc, site_id))

        groups: List[CorrelatedIncidentGroup] = []
        for provider, pairs in provider_map.items():
            distinct_sites = {site_id for _, site_id in pairs if site_id != "site-unknown"}
            if len(distinct_sites) >= 2:
                inc_list = [inc for inc, _ in pairs]
                inc_ids = [inc.incident_id for inc in inc_list]
                devices = list({inc.device_id for inc in inc_list} | {inc.interface for inc in inc_list})
                ev_ids, contra_ids = self._collect_evidence_ids(inc_list)

                # Deterministic confidence derivation
                conf = 0.70 + 0.05 * min(4, len(distinct_sites)) + 0.05 * min(3, len(ev_ids))
                if contra_ids:
                    conf -= 0.10 * min(2, len(contra_ids))
                conf = round(max(0.10, min(1.0, conf)), 2)

                groups.append(
                    CorrelatedIncidentGroup(
                        group_id=f"GRP-PROV-{provider.upper()}-{uuid.uuid4().hex[:6]}",
                        correlation_type=CorrelationType.SHARED_PROVIDER,
                        title=f"Shared Upstream Provider Degradation: {provider}",
                        description=f"Correlated {len(inc_ids)} active incidents across {len(distinct_sites)} sites ({', '.join(sorted(distinct_sites))}) experiencing carrier-level degradation on shared upstream provider {provider}.",
                        incident_ids=inc_ids,
                        affected_site_ids=sorted(list(distinct_sites)),
                        affected_devices=sorted(devices),
                        shared_dependency=provider,
                        correlation_confidence=conf,
                        primary_root_cause_hypothesis=f"Regional or transit carrier performance degradation on upstream {provider}.",
                        supporting_evidence_ids=ev_ids,
                        contradicting_evidence_ids=contra_ids,
                        recommended_coordinating_action=f"Evaluate failover to secondary WAN uplinks (e.g. ISP-B) across affected sites {', '.join(sorted(distinct_sites))}.",
                    )
                )

        return groups

    # -----------------------------------------------------------------------
    # Dimension 2: Shared Topology Dependency
    # -----------------------------------------------------------------------
    def _correlate_shared_topology(
        self, incidents: List[IncidentRecord]
    ) -> List[CorrelatedIncidentGroup]:
        """Correlate incidents sharing a common upstream transit node/hub in the topology graph."""
        dependency_map: Dict[str, List[Tuple[IncidentRecord, str]]] = {}

        for inc in incidents:
            site = self._inventory_service.get_site_for_device(inc.device_id) or self._inventory_service.get_site_for_device(inc.interface)
            site_id = site.site_id if site else "site-unknown"

            # Query upstream topology dependencies from graph
            ancestors = self._resolve_upstream_dependencies(inc.device_id)
            for ancestor_id in ancestors:
                if ancestor_id not in dependency_map:
                    dependency_map[ancestor_id] = []
                dependency_map[ancestor_id].append((inc, site_id))

        groups: List[CorrelatedIncidentGroup] = []
        for ancestor_id, pairs in dependency_map.items():
            distinct_sites = {site_id for _, site_id in pairs if site_id != "site-unknown"}
            if len(distinct_sites) >= 2:
                inc_list = [inc for inc, _ in pairs]
                inc_ids = [inc.incident_id for inc in inc_list]
                devices = list({inc.device_id for inc in inc_list} | {inc.interface for inc in inc_list})
                ev_ids, contra_ids = self._collect_evidence_ids(inc_list)

                conf = 0.75 + 0.05 * min(3, len(distinct_sites)) + 0.05 * min(2, len(ev_ids))
                if contra_ids:
                    conf -= 0.10 * min(2, len(contra_ids))
                conf = round(max(0.10, min(1.0, conf)), 2)

                groups.append(
                    CorrelatedIncidentGroup(
                        group_id=f"GRP-TOPO-{ancestor_id}-{uuid.uuid4().hex[:6]}",
                        correlation_type=CorrelationType.SHARED_TOPOLOGY_DEPENDENCY,
                        title=f"Shared Topology Transit Bottleneck: {ancestor_id}",
                        description=f"Correlated {len(inc_ids)} incidents across {len(distinct_sites)} sites sharing common upstream transit node {ancestor_id}.",
                        incident_ids=inc_ids,
                        affected_site_ids=sorted(list(distinct_sites)),
                        affected_devices=sorted(devices),
                        shared_dependency=ancestor_id,
                        correlation_confidence=conf,
                        primary_root_cause_hypothesis=f"Transit aggregation or forwarding fault located on shared parent node {ancestor_id}.",
                        supporting_evidence_ids=ev_ids,
                        contradicting_evidence_ids=contra_ids,
                        recommended_coordinating_action=f"Inspect upstream transit node {ancestor_id} and isolate traffic flows.",
                    )
                )

        return groups

    # -----------------------------------------------------------------------
    # Dimension 3: Similar Failure Signature
    # -----------------------------------------------------------------------
    def _correlate_similar_signature(
        self, incidents: List[IncidentRecord]
    ) -> List[CorrelatedIncidentGroup]:
        """Correlate incidents across distinct sites exhibiting matching deterministic signatures."""
        groups: List[CorrelatedIncidentGroup] = []
        signature_map: Dict[str, List[Tuple[IncidentRecord, str]]] = {}

        for inc in incidents:
            site = self._inventory_service.get_site_for_device(inc.device_id) or self._inventory_service.get_site_for_device(inc.interface)
            site_id = site.site_id if site else "site-unknown"

            # Derive signature key from incident type and failure signals
            sig_key = inc.incident_type or "GENERAL_ANOMALY"
            if inc.contributing_signals:
                primary_sig = sorted(inc.contributing_signals)[0]
                sig_key = f"{sig_key}:{primary_sig}"

            if sig_key not in signature_map:
                signature_map[sig_key] = []
            signature_map[sig_key].append((inc, site_id))

        for sig_key, pairs in signature_map.items():
            distinct_sites = {site_id for _, site_id in pairs if site_id != "site-unknown"}
            if len(distinct_sites) >= 2:
                inc_list = [inc for inc, _ in pairs]
                inc_ids = [inc.incident_id for inc in inc_list]
                devices = list({inc.device_id for inc in inc_list} | {inc.interface for inc in inc_list})
                ev_ids, contra_ids = self._collect_evidence_ids(inc_list)

                conf = 0.80 + 0.05 * min(2, len(distinct_sites)) + 0.05 * min(2, len(ev_ids))
                if contra_ids:
                    conf -= 0.10 * min(2, len(contra_ids))
                conf = round(max(0.10, min(1.0, conf)), 2)

                groups.append(
                    CorrelatedIncidentGroup(
                        group_id=f"GRP-SIG-{uuid.uuid4().hex[:6]}",
                        correlation_type=CorrelationType.SIMILAR_FAILURE_SIGNATURE,
                        title=f"Common Failure Pattern: {sig_key}",
                        description=f"Correlated {len(inc_ids)} incidents across {len(distinct_sites)} sites exhibiting matching failure pattern '{sig_key}'.",
                        incident_ids=inc_ids,
                        affected_site_ids=sorted(list(distinct_sites)),
                        affected_devices=sorted(devices),
                        shared_dependency=sig_key,
                        correlation_confidence=conf,
                        primary_root_cause_hypothesis=f"Synchronous operational or software failure matching signature pattern {sig_key}.",
                        supporting_evidence_ids=ev_ids,
                        contradicting_evidence_ids=contra_ids,
                        recommended_coordinating_action="Investigate common software or control-plane anomaly matching pattern signature.",
                    )
                )

        return groups

    # -----------------------------------------------------------------------
    # Dimension 4: Synchronized Temporal Anomaly
    # -----------------------------------------------------------------------
    def _correlate_synchronized_temporal(
        self, incidents: List[IncidentRecord]
    ) -> List[CorrelatedIncidentGroup]:
        """Correlate incidents occurring across distinct sites within <= 60 seconds of each other."""
        groups: List[CorrelatedIncidentGroup] = []
        if len(incidents) < 2:
            return groups

        # Pre-resolve site and timestamp once per incident
        inc_data = []
        for inc in incidents:
            site = self._inventory_service.get_site_for_device(inc.device_id) or self._inventory_service.get_site_for_device(inc.interface)
            site_id = site.site_id if site else "site-unknown"
            t = inc.created_at or inc.updated_at
            if t and site_id != "site-unknown":
                inc_data.append((inc, site_id, t))

        if len(inc_data) < 2:
            return groups

        # Sort by timestamp for linear sliding-window clustering
        inc_data.sort(key=lambda x: x[2])

        # Form continuous temporal clusters where adjacent events are within <= 60s
        temporal_clusters: List[List[Any]] = []
        current_cluster = [inc_data[0]]

        for k in range(1, len(inc_data)):
            prev_t = inc_data[k - 1][2]
            curr_t = inc_data[k][2]
            if (curr_t - prev_t).total_seconds() <= 60.0:
                current_cluster.append(inc_data[k])
            else:
                temporal_clusters.append(current_cluster)
                current_cluster = [inc_data[k]]
        if current_cluster:
            temporal_clusters.append(current_cluster)

        for cluster in temporal_clusters:
            if len(cluster) >= 2:
                distinct_sites = sorted(list({item[1] for item in cluster}))
                if len(distinct_sites) >= 2:
                    inc_list = [item[0] for item in cluster]
                    inc_ids = [item[0].incident_id for item in cluster]
                    devices = sorted(list({item[0].device_id for item in cluster} | {item[0].interface for item in cluster}))
                    ev_ids, contra_ids = self._collect_evidence_ids(inc_list)

                    delta_sec = (cluster[-1][2] - cluster[0][2]).total_seconds()
                    conf = 0.70 + 0.05 * min(4, len(ev_ids))
                    if contra_ids:
                        conf -= 0.10 * min(2, len(contra_ids))
                    conf = round(max(0.10, min(1.0, conf)), 2)

                    groups.append(
                        CorrelatedIncidentGroup(
                            group_id=f"GRP-TEMP-{uuid.uuid4().hex[:6]}",
                            correlation_type=CorrelationType.SYNCHRONIZED_TEMPORAL,
                            title=f"Coincident Temporal Degradation (Δt={delta_sec:.0f}s)",
                            description=f"Correlated coincident anomalies across {', '.join(distinct_sites)} detected within {delta_sec:.1f}s window.",
                            incident_ids=inc_ids,
                            affected_site_ids=distinct_sites,
                            affected_devices=devices,
                            shared_dependency=f"Coincident Window (Δt={delta_sec:.0f}s)",
                            correlation_confidence=conf,
                            primary_root_cause_hypothesis="Simultaneous multi-site disruption caused by common external trigger.",
                            supporting_evidence_ids=ev_ids,
                            contradicting_evidence_ids=contra_ids,
                            recommended_coordinating_action="Correlate external network events, provider maintenance, or power events.",
                        )
                    )

        return groups

    # -----------------------------------------------------------------------
    # Deduplication & Merging Engine
    # -----------------------------------------------------------------------
    def _deduplicate_and_merge(
        self, groups: List[CorrelatedIncidentGroup]
    ) -> List[CorrelatedIncidentGroup]:
        """
        Merge raw correlation candidate groups that share identical or subset incident clusters.
        """
        if not groups:
            return []

        merged: List[CorrelatedIncidentGroup] = []
        # Priority weighting for primary correlation type
        type_priority = {
            CorrelationType.SHARED_PROVIDER: 4,
            CorrelationType.SHARED_TOPOLOGY_DEPENDENCY: 3,
            CorrelationType.SIMILAR_FAILURE_SIGNATURE: 2,
            CorrelationType.SYNCHRONIZED_TEMPORAL: 1,
        }

        # Cluster by matching incident sets
        clusters: List[List[CorrelatedIncidentGroup]] = []

        for grp in groups:
            grp_set = set(grp.incident_ids)
            matched_cluster = None

            for cluster in clusters:
                cluster_inc_set = set()
                for c_grp in cluster:
                    cluster_inc_set.update(c_grp.incident_ids)

                # Overlap test: if sets share incidents or same shared_dependency
                if grp_set.intersection(cluster_inc_set) or (
                    grp.shared_dependency and any(c.shared_dependency == grp.shared_dependency for c in cluster)
                ):
                    matched_cluster = cluster
                    break

            if matched_cluster is not None:
                matched_cluster.append(grp)
            else:
                clusters.append([grp])

        for cluster in clusters:
            if len(cluster) == 1:
                merged.append(cluster[0])
            else:
                # Sort by type priority descending, then confidence descending
                cluster.sort(
                    key=lambda g: (type_priority.get(g.correlation_type, 0), g.correlation_confidence),
                    reverse=True,
                )
                primary = cluster[0]

                # Aggregate all incident IDs, site IDs, devices, and evidence
                all_incs: Set[str] = set()
                all_sites: Set[str] = set()
                all_devs: Set[str] = set()
                all_supp_ev: Set[str] = set()
                all_contra_ev: Set[str] = set()
                secondary_types: Set[CorrelationType] = set()

                for g in cluster:
                    all_incs.update(g.incident_ids)
                    all_sites.update(g.affected_site_ids)
                    all_devs.update(g.affected_devices)
                    all_supp_ev.update(g.supporting_evidence_ids)
                    all_contra_ev.update(g.contradicting_evidence_ids)
                    if g.correlation_type != primary.correlation_type:
                        secondary_types.add(g.correlation_type)

                # Composite boosted confidence
                combined_conf = primary.correlation_confidence + 0.05 * len(secondary_types)
                combined_conf = round(min(1.0, combined_conf), 2)

                merged_group = CorrelatedIncidentGroup(
                    group_id=primary.group_id,
                    correlation_type=primary.correlation_type,
                    title=primary.title,
                    description=primary.description,
                    incident_ids=sorted(list(all_incs)),
                    affected_site_ids=sorted(list(all_sites)),
                    affected_devices=sorted(list(all_devs)),
                    shared_dependency=primary.shared_dependency,
                    correlation_confidence=combined_conf,
                    primary_root_cause_hypothesis=primary.primary_root_cause_hypothesis,
                    supporting_evidence_ids=sorted(list(all_supp_ev)),
                    contradicting_evidence_ids=sorted(list(all_contra_ev)),
                    recommended_coordinating_action=primary.recommended_coordinating_action,
                    created_at=primary.created_at,
                    secondary_correlation_types=sorted(list(secondary_types), key=lambda t: type_priority.get(t, 0), reverse=True),
                )
                merged.append(merged_group)

        return merged

    # -----------------------------------------------------------------------
    # Helper Resolution Methods
    # -----------------------------------------------------------------------
    def _extract_providers_for_incident(
        self, inc: IncidentRecord, site: Optional[Any]
    ) -> List[str]:
        """Extract or resolve associated WAN providers for an incident."""
        providers = set()
        text = f"{inc.title} {inc.description} {' '.join(inc.contributing_signals)}".upper()

        if "ISP-A" in text or "ISPA" in text or "PRIMARY" in text:
            providers.add("ISP-A")
        if "ISP-B" in text or "ISPB" in text or "BACKUP" in text or "SECONDARY" in text:
            providers.add("ISP-B")

        # Check explicit metadata
        if inc.metadata and "provider" in inc.metadata:
            providers.add(str(inc.metadata["provider"]).upper())

        # If no explicit provider named in text, fallback to site's configured primary provider
        if not providers and site and hasattr(site, "primary_providers") and site.primary_providers:
            providers.add(site.primary_providers[0])

        return list(providers)

    def _resolve_upstream_dependencies(self, device_id: str) -> List[str]:
        """Query upstream topology ancestors for a device node."""
        ancestors: List[str] = []
        try:
            nodes = self._topology_service.find_upstream_dependencies(device_id)
            ancestors = [n.node_id for n in nodes if hasattr(n, "node_id")]
        except Exception as e:
            logger.debug(f"Topology dependency lookup failed for '{device_id}': {e}")

        # Fallback to topology repository graph if available
        if not ancestors:
            try:
                graph = self._topology_service.repository.get_graph()
                if graph and hasattr(graph, "get_upstream_nodes"):
                    ancestors = graph.get_upstream_nodes(device_id)
            except Exception:
                pass

        return ancestors

    def _collect_evidence_ids(
        self, incidents: List[IncidentRecord]
    ) -> Tuple[List[str], List[str]]:
        """Collect preserved supporting and contradicting evidence IDs from incidents and registry."""
        supporting: Set[str] = set()
        contradicting: Set[str] = set()

        for inc in incidents:
            # 1. From incident metadata
            if inc.metadata and "evidence_ids" in inc.metadata:
                for eid in inc.metadata["evidence_ids"]:
                    supporting.add(str(eid))
            if inc.metadata and "contradicting_evidence_ids" in inc.metadata:
                for eid in inc.metadata["contradicting_evidence_ids"]:
                    contradicting.add(str(eid))

            # 2. From incident timeline metadata
            for tl in inc.timeline:
                if tl.metadata and "evidence_id" in tl.metadata:
                    supporting.add(str(tl.metadata["evidence_id"]))

            # 3. From evidence registry by incident_id or device_id
            try:
                refs = self._evidence_registry.get_evidence_for_incident(inc.incident_id)
                for r in refs:
                    if hasattr(r, "relationship_to_hypothesis") and str(r.relationship_to_hypothesis).upper() == "CONTRADICTING":
                        contradicting.add(r.evidence_id)
                    else:
                        supporting.add(r.evidence_id)
            except Exception:
                pass

        return sorted(list(supporting)), sorted(list(contradicting))
