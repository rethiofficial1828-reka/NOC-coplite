"""
Deterministic Incident Prioritization Service for Multi-Site NOC Command Center (v1.3 Phase 3).

Calculates deterministic multi-factor priority scores for operator work queues:
Score = 0.30 * severity + 0.25 * failure_risk + 0.20 * blast_radius + 0.15 * tti_urgency + 0.10 * correlation

Strictly read-only and advisory. Does not grant execution authority or alter autonomy policies.
"""

from datetime import datetime, timezone
import math
import threading
from typing import Any, Dict, List, Optional, Set, Tuple

from agents.core.logger import get_agent_logger
from agents.incident.incident_models import (
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)
from agents.multi_site.multi_site_models import (
    CorrelatedIncidentGroup,
    QueuePriority,
    WorkQueueItem,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.topology.topology_models import ImpactSeverity
from agents.topology.topology_service import TopologyService

logger = get_agent_logger("IncidentPrioritizationService")


class IncidentPrioritizationService:
    """
    Deterministic priority scoring and work queue generation service.
    Ranks operator tasks objectively across multi-site fleets.
    """

    def __init__(
        self,
        inventory_service: Optional[MultiSiteInventoryService] = None,
        topology_service: Optional[TopologyService] = None,
    ) -> None:
        self._inventory_service = inventory_service or MultiSiteInventoryService()
        self._topology_service = topology_service or TopologyService()
        self._lock = threading.RLock()

    def prioritize_incidents(
        self,
        incidents: List[IncidentRecord],
        correlated_groups: Optional[List[CorrelatedIncidentGroup]] = None,
    ) -> List[WorkQueueItem]:
        """
        Produce prioritized, deterministically sorted WorkQueueItem list.

        Args:
            incidents: List of IncidentRecords.
            correlated_groups: Optional list of active CorrelatedIncidentGroups.

        Returns:
            List of WorkQueueItem objects sorted by priority score and tie-breakers.
        """
        with self._lock:
            if not incidents:
                return []

            # Map incident IDs to their correlated group IDs if present
            corr_map: Dict[str, str] = {}
            if correlated_groups:
                for grp in correlated_groups:
                    for inc_id in grp.incident_ids:
                        corr_map[inc_id] = grp.group_id

            queue_items: List[WorkQueueItem] = []
            for inc in incidents:
                item = self._score_and_build_item(inc, corr_map.get(inc.incident_id))
                queue_items.append(item)

            # Sort with deterministic multi-level tie breaking
            queue_items.sort(key=self._tie_break_key)
            return queue_items

    def compute_priority_score(
        self,
        severity: IncidentSeverity,
        risk_score: float,
        blast_radius: ImpactSeverity,
        time_to_impact: Optional[float],
        is_correlated: bool,
    ) -> Tuple[float, QueuePriority]:
        """
        Public deterministic priority score calculation function.

        Returns:
            Tuple of (priority_score, QueuePriority).
        """
        # 1. Severity Normalization (weight = 0.30)
        sev_weights = {
            IncidentSeverity.CRITICAL: 1.0,
            IncidentSeverity.HIGH: 0.75,
            IncidentSeverity.MEDIUM: 0.50,
            IncidentSeverity.LOW: 0.25,
            IncidentSeverity.INFO: 0.10,
        }
        s_norm = sev_weights.get(severity, 0.50)

        # 2. Risk Normalization (weight = 0.25)
        r_norm = max(0.0, min(1.0, float(risk_score) if risk_score is not None else 0.0))

        # 3. Blast Radius Normalization (weight = 0.20)
        blast_weights = {
            ImpactSeverity.CRITICAL: 1.0,
            ImpactSeverity.HIGH: 0.75,
            ImpactSeverity.MEDIUM: 0.50,
            ImpactSeverity.LOW: 0.25,
            ImpactSeverity.NONE: 0.10,
        }
        b_norm = blast_weights.get(blast_radius, 0.25)

        # 4. Time To Impact Urgency Normalization (weight = 0.15)
        if time_to_impact is not None and time_to_impact > 0:
            tti_urgency = math.exp(-float(time_to_impact) / 300.0)
        else:
            # Deterministic neutral urgency (e^(-1) = ~0.368) without fabricating urgency
            tti_urgency = math.exp(-1.0)

        # 5. Correlation Normalization (weight = 0.10)
        c_norm = 1.0 if is_correlated else 0.0

        # Composite Priority Score calculation
        raw_score = (
            (0.30 * s_norm)
            + (0.25 * r_norm)
            + (0.20 * b_norm)
            + (0.15 * tti_urgency)
            + (0.10 * c_norm)
        )
        score = round(max(0.0, min(1.0, raw_score)), 4)

        # Queue Tier Mapping
        if score >= 0.80 or severity == IncidentSeverity.CRITICAL:
            tier = QueuePriority.CRITICAL
        elif score >= 0.60:
            tier = QueuePriority.HIGH
        elif score >= 0.40:
            tier = QueuePriority.MEDIUM
        else:
            tier = QueuePriority.LOW

        return score, tier

    def _score_and_build_item(
        self,
        inc: IncidentRecord,
        correlated_group_id: Optional[str] = None,
    ) -> WorkQueueItem:
        """Score an individual incident and construct the complete WorkQueueItem."""
        # 1. Resolve site information
        site = self._inventory_service.get_site_for_device(inc.device_id) or self._inventory_service.get_site_for_device(inc.interface)
        site_id = site.site_id if site else "site-unknown"
        site_name = site.site_name if site else "Unknown Site"

        # 2. Resolve blast radius
        blast = self._resolve_blast_radius(inc)

        # 3. Resolve TTI & Risk
        r_val = float(inc.risk_score) if inc.risk_score is not None else 0.0
        tti_val = float(inc.time_to_impact) if inc.time_to_impact is not None and inc.time_to_impact > 0 else -1.0

        # 4. Compute composite priority score & tier
        is_corr = correlated_group_id is not None
        score, tier = self.compute_priority_score(
            severity=inc.severity,
            risk_score=r_val,
            blast_radius=blast,
            time_to_impact=tti_val if tti_val > 0 else None,
            is_correlated=is_corr,
        )

        return WorkQueueItem(
            incident_id=inc.incident_id,
            site_id=site_id,
            site_name=site_name,
            device_id=inc.device_id,
            interface=inc.interface,
            title=inc.title,
            priority=tier,
            priority_score=score,
            severity=inc.severity,
            risk_score=r_val,
            blast_radius_severity=blast,
            time_to_impact_sec=tti_val,
            trust_requirement="HUMAN_APPROVAL_REQUIRED",
            status=inc.status,
            created_at=inc.created_at or datetime.now(timezone.utc),
            correlated_group_id=correlated_group_id,
        )

    def _resolve_blast_radius(self, inc: IncidentRecord) -> ImpactSeverity:
        """Resolve topology blast radius severity for the incident."""
        if inc.metadata and "blast_radius_severity" in inc.metadata:
            raw = str(inc.metadata["blast_radius_severity"]).upper()
            try:
                return ImpactSeverity(raw)
            except ValueError:
                pass

        # Query topology service if available
        try:
            topo_impact = self._topology_service.calculate_blast_radius(inc.device_id)
            if topo_impact and hasattr(topo_impact, "severity"):
                sev = getattr(topo_impact, "severity")
                if isinstance(sev, ImpactSeverity):
                    return sev
                elif isinstance(sev, str):
                    try:
                        return ImpactSeverity(sev.upper())
                    except ValueError:
                        pass
        except Exception:
            pass

        # Fallback to incident severity heuristic
        if inc.severity == IncidentSeverity.CRITICAL:
            return ImpactSeverity.CRITICAL
        elif inc.severity == IncidentSeverity.HIGH:
            return ImpactSeverity.HIGH
        elif inc.severity == IncidentSeverity.MEDIUM:
            return ImpactSeverity.MEDIUM
        return ImpactSeverity.LOW

    def _tie_break_key(self, item: WorkQueueItem) -> Tuple[float, int, float, float, str]:
        """
        Deterministic tie-breaking comparator key for descending queue sorting:
        1. priority_score (descending -> negative float)
        2. severity rank (descending -> negative int)
        3. time_to_impact (ascending -> shorter TTI first; missing/negative ranked last)
        4. created_at (ascending -> earlier timestamp first)
        5. incident_id (ascending -> lexical order)
        """
        sev_rank = {
            IncidentSeverity.CRITICAL: 5,
            IncidentSeverity.HIGH: 4,
            IncidentSeverity.MEDIUM: 3,
            IncidentSeverity.LOW: 2,
            IncidentSeverity.INFO: 1,
        }.get(item.severity, 0)

        # For TTI, positive numbers sort in ascending order; -1 (missing) sorts as infinity (1e9)
        tti_sort = item.time_to_impact_sec if item.time_to_impact_sec > 0 else 1e9

        # Created timestamp as unix epoch
        t_epoch = item.created_at.timestamp() if item.created_at else 0.0

        return (-item.priority_score, -sev_rank, tti_sort, t_epoch, item.incident_id)
