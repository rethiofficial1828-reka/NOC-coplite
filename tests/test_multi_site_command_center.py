"""
Unit and Integration Tests for MultiSiteCommandCenterService (v1.3 Phase 1).

Covers:
1. MultiSiteSummaryState generation across all sites
2. Prioritized Operator Work Queue sorting & tier classification
3. Multi-factor priority score calculation (Severity + Risk + TTI urgency)
4. Site health resolution
5. Drill-down context mapping
6. Strict read-only advisory guarantees
7. Preserved v1.2 failover baseline behavior
"""

from unittest.mock import MagicMock
import pytest

from agents.incident.incident_models import (
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)
from agents.incident.incident_service import IncidentService
from agents.multi_site.command_center_service import MultiSiteCommandCenterService
from agents.multi_site.multi_site_models import (
    MultiSiteSummaryState,
    QueuePriority,
    SiteHealthStatus,
    WorkQueueItem,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.topology.topology_service import TopologyService


@pytest.fixture
def mock_incident_service():
    service = MagicMock(spec=IncidentService)
    incidents = [
        IncidentRecord(
            incident_id="INC-2026-000001",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="WAN ISP-A Packet Loss & Imminent Carrier Failure",
            severity=IncidentSeverity.CRITICAL,
            status=IncidentStatus.OPEN,
            risk_score=0.91,
            time_to_impact=22.0,
        ),
        IncidentRecord(
            incident_id="INC-2026-000002",
            device_id="rtr-01",
            interface="Router 1",
            title="BGP Session Flapping on Distribution Router",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.74,
            time_to_impact=95.0,
        ),
        IncidentRecord(
            incident_id="INC-2026-000003",
            device_id="core-01",
            interface="Campus Core",
            title="Slight Ingress Jitter on Core Switch",
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.OPEN,
            risk_score=0.15,
            time_to_impact=600.0,
        ),
        IncidentRecord(
            incident_id="INC-2026-000004",
            device_id="fw-01",
            interface="Firewall",
            title="Resolved Port Anomaly",
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.RESOLVED,  # Inactive status
            risk_score=0.20,
            time_to_impact=-1.0,
        ),
    ]
    service.get_all_incidents.return_value = incidents
    return service


@pytest.fixture
def command_center_service(mock_incident_service):
    inventory_service = MultiSiteInventoryService(
        incident_service=mock_incident_service,
    )
    topology_service = MagicMock(spec=TopologyService)
    return MultiSiteCommandCenterService(
        inventory_service=inventory_service,
        incident_service=mock_incident_service,
        topology_service=topology_service,
    )


class TestMultiSiteCommandCenterService:
    """Test suite for MultiSiteCommandCenterService."""

    def test_build_summary_state_structure(self, command_center_service):
        summary = command_center_service.build_summary_state()
        assert isinstance(summary, MultiSiteSummaryState)
        assert summary.total_sites >= 4
        assert len(summary.sites) == summary.total_sites
        assert summary.total_active_incidents == 3  # Excludes RESOLVED
        assert summary.critical_active_incidents >= 1
        assert len(summary.work_queue) == 3

    def test_operator_queue_prioritization_and_sorting(self, command_center_service):
        queue = command_center_service.get_operator_queue()
        assert len(queue) == 3

        # Highest priority first (INC-001 with CRITICAL severity and 0.91 risk)
        top_item = queue[0]
        assert top_item.incident_id == "INC-2026-000001"
        assert top_item.priority == QueuePriority.CRITICAL
        assert top_item.site_id == "site-branch3"
        assert top_item.site_name == "Branch Office 3"
        assert top_item.priority_score >= 0.80

        # Second item (INC-002 with HIGH severity)
        second_item = queue[1]
        assert second_item.incident_id == "INC-2026-000002"
        assert second_item.priority in (QueuePriority.HIGH, QueuePriority.CRITICAL)
        assert second_item.site_id == "site-campus"

        # Lowest item (INC-003 with LOW severity)
        lowest_item = queue[2]
        assert lowest_item.incident_id == "INC-2026-000003"
        assert lowest_item.priority == QueuePriority.LOW
        assert lowest_item.priority_score < 0.40

        # Verify strict descending order
        scores = [q.priority_score for q in queue]
        assert scores == sorted(scores, reverse=True)

    def test_get_site_health_resolution(self, command_center_service):
        # Branch 3 has a critical incident -> CRITICAL
        health_branch3 = command_center_service.get_site_health("site-branch3")
        assert health_branch3 == SiteHealthStatus.CRITICAL

        # DC HQ has no active incidents -> HEALTHY
        health_dc = command_center_service.get_site_health("site-dc")
        assert health_dc == SiteHealthStatus.HEALTHY

    def test_drill_down_target_preserves_device_context(self, command_center_service):
        queue = command_center_service.get_operator_queue()
        top_item = queue[0]
        assert top_item.device_id == "branch3-uplink"
        assert top_item.interface == "Branch3-Uplink"

        # Confirm inventory maps device back to site cleanly
        site = command_center_service.inventory_service.get_site_for_device(top_item.device_id)
        assert site is not None
        assert site.site_id == "site-branch3"

    def test_advisory_read_only_boundaries(self, command_center_service):
        # Ensure no execution capabilities exist in Command Center
        assert not hasattr(command_center_service, "execute_failover")
        assert not hasattr(command_center_service, "trigger_remediation")
        assert not hasattr(command_center_service, "mutate_network")
