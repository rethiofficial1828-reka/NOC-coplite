"""
Multi-Site Command Center Service Module for NOC-Copilot v1.3.

Provides top-level fleet health aggregation, operator work queue synthesis,
cross-site incident correlation, deterministic queue prioritization,
and unified summary state generation for the UI.
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
import threading

from agents.core.logger import get_agent_logger
from agents.incident.incident_models import IncidentRecord, IncidentSeverity, IncidentStatus
from agents.incident.incident_service import IncidentService
from agents.multi_site.cross_site_correlator import CrossSiteCorrelationService
from agents.multi_site.incident_prioritizer import IncidentPrioritizationService
from agents.multi_site.multi_site_models import (
    CorrelatedIncidentGroup,
    MultiSiteSummaryState,
    QueuePriority,
    SiteHealthStatus,
    SiteRecord,
    WorkQueueItem,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.topology.topology_models import ImpactSeverity
from agents.topology.topology_service import TopologyService

logger = get_agent_logger("MultiSiteCommandCenterService")


class MultiSiteCommandCenterService:
    """
    Facade and orchestration service for the Multi-Site NOC Command Center.
    Aggregates multi-site inventory, active incident queues, cross-site correlations,
    deterministic prioritization, and health summaries.
    """

    def __init__(
        self,
        inventory_service: Optional[MultiSiteInventoryService] = None,
        incident_service: Optional[IncidentService] = None,
        topology_service: Optional[TopologyService] = None,
        correlator: Optional[CrossSiteCorrelationService] = None,
        prioritizer: Optional[IncidentPrioritizationService] = None,
    ) -> None:
        self._inventory_service = inventory_service or MultiSiteInventoryService()
        self._incident_service = incident_service or IncidentService()
        self._topology_service = topology_service or TopologyService()
        self._correlator = correlator or CrossSiteCorrelationService(
            inventory_service=self._inventory_service,
            incident_service=self._incident_service,
            topology_service=self._topology_service,
        )
        self._prioritizer = prioritizer or IncidentPrioritizationService(
            inventory_service=self._inventory_service,
            topology_service=self._topology_service,
        )
        self._lock = threading.RLock()

    @property
    def inventory_service(self) -> MultiSiteInventoryService:
        """Underlying inventory service instance."""
        return self._inventory_service

    @property
    def incident_service(self) -> IncidentService:
        """Underlying incident service instance."""
        return self._incident_service

    @property
    def correlator(self) -> CrossSiteCorrelationService:
        """Underlying cross-site correlation service instance."""
        return self._correlator

    @property
    def prioritizer(self) -> IncidentPrioritizationService:
        """Underlying incident prioritization service instance."""
        return self._prioritizer

    def build_summary_state(self) -> MultiSiteSummaryState:
        """
        Synthesize the complete multi-site command center summary snapshot.

        Returns:
            MultiSiteSummaryState object.
        """
        with self._lock:
            sites = self._inventory_service.get_all_sites(evaluate_health=True)
            correlated_groups = self.get_correlated_groups()
            work_queue = self.get_operator_queue(correlated_groups=correlated_groups)

            total_sites = len(sites)
            healthy = sum(1 for s in sites if s.health_status == SiteHealthStatus.HEALTHY)
            degraded = sum(1 for s in sites if s.health_status == SiteHealthStatus.DEGRADED)
            critical = sum(1 for s in sites if s.health_status == SiteHealthStatus.CRITICAL)
            offline = sum(1 for s in sites if s.health_status == SiteHealthStatus.OFFLINE)

            total_active_incidents = len(work_queue)
            critical_active_incidents = sum(
                1 for item in work_queue if item.severity == IncidentSeverity.CRITICAL or item.priority == QueuePriority.CRITICAL
            )

            return MultiSiteSummaryState(
                total_sites=total_sites,
                healthy_sites=healthy,
                degraded_sites=degraded,
                critical_sites=critical,
                offline_sites=offline,
                total_active_incidents=total_active_incidents,
                critical_active_incidents=critical_active_incidents,
                sites=sites,
                work_queue=work_queue,
                correlated_groups=correlated_groups,
                timestamp=datetime.now(timezone.utc),
            )

    def get_operator_queue(
        self, correlated_groups: Optional[List[CorrelatedIncidentGroup]] = None
    ) -> List[WorkQueueItem]:
        """
        Generate prioritized operator work queue from all active incidents across all sites.

        Returns:
            List of WorkQueueItem objects sorted deterministically by priority score and tie breakers.
        """
        with self._lock:
            active_statuses = (
                IncidentStatus.NEW,
                IncidentStatus.OPEN,
                IncidentStatus.ACKNOWLEDGED,
                IncidentStatus.IN_PROGRESS,
            )

            try:
                all_incidents = self._incident_service.get_all_incidents()
                target_incs = [i for i in all_incidents if i.status in active_statuses]
                if correlated_groups is None:
                    correlated_groups = self.get_correlated_groups()
                return self._prioritizer.prioritize_incidents(target_incs, correlated_groups)
            except Exception as e:
                logger.error(f"Error generating prioritized operator queue: {e}")
                return []

    def get_correlated_groups(self) -> List[CorrelatedIncidentGroup]:
        """
        Retrieve correlated cross-site incident clusters from CrossSiteCorrelationService.
        """
        with self._lock:
            try:
                return self._correlator.correlate_active_incidents()
            except Exception as e:
                logger.error(f"Error querying cross-site correlation groups: {e}")
                return []

    def get_site_health(self, site_id: str) -> SiteHealthStatus:
        """
        Retrieve aggregate health status for a specific site.

        Args:
            site_id: Site identifier.

        Returns:
            SiteHealthStatus enum value.
        """
        site = self._inventory_service.get_site(site_id, evaluate_health=True)
        if site:
            return site.health_status
        return SiteHealthStatus.OFFLINE
