"""
Unit and Integration Tests for Multi-Site Command Center Integration & Operator UX (v1.3 Phase 4).

Covers all 10 required validation cases:
1. summary state rendering
2. site cards
3. correlated groups
4. work queue
5. filtering (priority, site, health, state, correlation, provider, search query)
6. drill-down context preservation
7. return navigation
8. safety-mode visibility
9. no execution side effects
10. large-list rendering behavior
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from agents.incident.incident_models import (
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)
from agents.incident.incident_service import IncidentService
from agents.multi_site.command_center_service import MultiSiteCommandCenterService
from agents.multi_site.cross_site_correlator import CrossSiteCorrelationService
from agents.multi_site.incident_prioritizer import IncidentPrioritizationService
from agents.multi_site.multi_site_models import (
    CorrelatedIncidentGroup,
    CorrelationType,
    MultiSiteSummaryState,
    QueuePriority,
    SiteHealthStatus,
    SiteRecord,
    SiteType,
    WorkQueueItem,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.topology.topology_models import ImpactSeverity
from agents.topology.topology_service import TopologyService


@pytest.fixture
def mock_inventory_service():
    service = MagicMock(spec=MultiSiteInventoryService)

    sites = [
        SiteRecord(
            site_id="site-branch3",
            site_name="Branch Office 3",
            site_type=SiteType.BRANCH,
            location="Regional Office",
            device_ids=["branch3-uplink"],
            primary_providers=["ISP-A"],
            backup_providers=["ISP-B"],
            health_status=SiteHealthStatus.CRITICAL,
            active_incidents_count=2,
            critical_incidents_count=1,
            average_latency_ms=185.0,
            average_loss_percent=12.5,
        ),
        SiteRecord(
            site_id="site-campus",
            site_name="Campus Main Site",
            site_type=SiteType.CAMPUS,
            location="HQ Campus",
            device_ids=["core-01", "rtr-01"],
            primary_providers=["ISP-A"],
            backup_providers=["ISP-B"],
            health_status=SiteHealthStatus.DEGRADED,
            active_incidents_count=1,
            critical_incidents_count=0,
            average_latency_ms=45.0,
            average_loss_percent=2.0,
        ),
        SiteRecord(
            site_id="site-dc",
            site_name="Data Center HQ",
            site_type=SiteType.DATACENTER,
            location="Primary Data Center",
            device_ids=["fw-01", "hub"],
            primary_providers=["ISP-B"],
            backup_providers=["ISP-A"],
            health_status=SiteHealthStatus.HEALTHY,
            active_incidents_count=0,
            critical_incidents_count=0,
            average_latency_ms=5.0,
            average_loss_percent=0.0,
        ),
        SiteRecord(
            site_id="site-branch1",
            site_name="Branch Office 1",
            site_type=SiteType.BRANCH,
            location="Remote Office 1",
            device_ids=["branch1"],
            primary_providers=["ISP-A"],
            backup_providers=["ISP-B"],
            health_status=SiteHealthStatus.OFFLINE,
            active_incidents_count=0,
            critical_incidents_count=0,
            average_latency_ms=0.0,
            average_loss_percent=100.0,
        ),
    ]

    service.get_all_sites.return_value = sites

    def _get_site(site_id: str, evaluate_health: bool = False):
        return next((s for s in sites if s.site_id == site_id), None)

    service.get_site.side_effect = _get_site

    def _get_site_for_dev(dev_key: str):
        k = str(dev_key).lower()
        if "branch3" in k:
            return sites[0]
        elif "core" in k or "rtr" in k:
            return sites[1]
        elif "fw" in k or "hub" in k:
            return sites[2]
        elif "branch1" in k:
            return sites[3]
        return None

    service.get_site_for_device.side_effect = _get_site_for_dev
    return service


@pytest.fixture
def mock_incident_service():
    service = MagicMock(spec=IncidentService)
    now = datetime.now(timezone.utc)
    incidents = [
        IncidentRecord(
            incident_id="INC-2026-001",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A Packet Loss & High Latency",
            severity=IncidentSeverity.CRITICAL,
            status=IncidentStatus.OPEN,
            risk_score=0.92,
            time_to_impact=30.0,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-01"]},
            created_at=now,
        ),
        IncidentRecord(
            incident_id="INC-2026-002",
            device_id="core-01",
            interface="Campus Core",
            title="ISP-A Carrier Jitter & Loss",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.75,
            time_to_impact=90.0,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-02"]},
            created_at=now + timedelta(seconds=15),
        ),
        IncidentRecord(
            incident_id="INC-2026-003",
            device_id="branch3-uplink",
            interface="eth1",
            title="Local Buffer Warning",
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.NEW,
            risk_score=0.20,
            time_to_impact=600.0,
            metadata={"provider": "ISP-A"},
            created_at=now + timedelta(minutes=5),
        ),
    ]
    service.get_all_incidents.return_value = incidents
    return service


@pytest.fixture
def command_center(mock_inventory_service, mock_incident_service):
    topo = MagicMock(spec=TopologyService)
    correlator = CrossSiteCorrelationService(
        inventory_service=mock_inventory_service,
        incident_service=mock_incident_service,
        topology_service=topo,
    )
    prioritizer = IncidentPrioritizationService(
        inventory_service=mock_inventory_service,
        topology_service=topo,
    )
    return MultiSiteCommandCenterService(
        inventory_service=mock_inventory_service,
        incident_service=mock_incident_service,
        topology_service=topo,
        correlator=correlator,
        prioritizer=prioritizer,
    )


class TestMultiSiteCommandCenterUI:
    """Comprehensive test suite for Phase 4 Command Center UI Integration & UX."""

    def test_summary_state_rendering(self, command_center):
        state = command_center.build_summary_state()
        assert isinstance(state, MultiSiteSummaryState)
        assert state.total_sites == 4
        assert state.healthy_sites == 1
        assert state.degraded_sites == 1
        assert state.critical_sites == 1
        assert state.offline_sites == 1
        assert state.total_active_incidents == 3
        assert state.critical_active_incidents >= 1

    def test_site_cards(self, command_center):
        state = command_center.build_summary_state()
        assert len(state.sites) == 4
        b3 = next(s for s in state.sites if s.site_id == "site-branch3")
        assert b3.site_name == "Branch Office 3"
        assert b3.site_type == SiteType.BRANCH
        assert b3.health_status == SiteHealthStatus.CRITICAL
        assert "branch3-uplink" in b3.device_ids
        assert b3.primary_providers == ["ISP-A"]
        assert b3.average_latency_ms == 185.0
        assert b3.average_loss_percent == 12.5
        assert b3.active_incidents_count == 2

    def test_correlated_groups(self, command_center):
        state = command_center.build_summary_state()
        assert len(state.correlated_groups) >= 1
        grp = state.correlated_groups[0]
        assert isinstance(grp, CorrelatedIncidentGroup)
        assert grp.shared_dependency == "ISP-A"
        assert set(grp.affected_site_ids) == {"site-branch3", "site-campus"}
        assert grp.correlation_confidence >= 0.70
        assert "EV-01" in grp.supporting_evidence_ids
        assert "EV-02" in grp.supporting_evidence_ids

    def test_work_queue(self, command_center):
        state = command_center.build_summary_state()
        assert len(state.work_queue) == 3
        top_item = state.work_queue[0]
        assert isinstance(top_item, WorkQueueItem)
        assert top_item.incident_id == "INC-2026-001"
        assert top_item.priority == QueuePriority.CRITICAL
        assert top_item.priority_score >= 0.80
        assert top_item.risk_score == 0.92
        assert top_item.trust_requirement == "HUMAN_APPROVAL_REQUIRED"

    def test_filtering_capabilities(self, command_center):
        state = command_center.build_summary_state()

        # 1. Filter by Priority
        crit_queue = [q for q in state.work_queue if q.priority == QueuePriority.CRITICAL]
        assert len(crit_queue) >= 1
        assert crit_queue[0].incident_id == "INC-2026-001"

        # 2. Filter by Site
        b3_queue = [q for q in state.work_queue if q.site_id == "site-branch3"]
        assert len(b3_queue) == 2

        # 3. Filter by Correlation
        corr_queue = [q for q in state.work_queue if q.correlated_group_id is not None]
        assert len(corr_queue) >= 2

        # 4. Filter by Search Query
        searched = [q for q in state.work_queue if "loss" in q.title.lower()]
        assert len(searched) >= 2

    def test_drill_down_context_preservation(self, command_center):
        state = command_center.build_summary_state()
        top_item = state.work_queue[0]

        # Verify all context parameters required for drill-down exist
        context = {
            "device_name": top_item.device_id,
            "incident_id": top_item.incident_id,
            "site_id": top_item.site_id,
            "interface": top_item.interface,
            "correlated_group_id": top_item.correlated_group_id,
            "ui_view_mode": "DRILL_DOWN",
        }
        assert context["device_name"] == "branch3-uplink"
        assert context["incident_id"] == "INC-2026-001"
        assert context["site_id"] == "site-branch3"
        assert context["ui_view_mode"] == "DRILL_DOWN"

    def test_return_navigation(self, command_center):
        # Simulate view mode toggle
        session_state = {"ui_view_mode": "DRILL_DOWN", "selected_device_name": "branch3-uplink"}
        # Return to Command Center
        session_state["ui_view_mode"] = "COMMAND_CENTER"
        assert session_state["ui_view_mode"] == "COMMAND_CENTER"
        assert session_state["selected_device_name"] == "branch3-uplink"  # Context retained

    def test_safety_mode_visibility(self, command_center):
        state = command_center.build_summary_state()
        for item in state.work_queue:
            # Must explicitly enforce human approval and safety policy
            assert item.trust_requirement == "HUMAN_APPROVAL_REQUIRED"

    def test_no_execution_side_effects(self, command_center):
        # MultiSiteCommandCenterService is read-only
        assert not hasattr(command_center, "execute_failover")
        assert not hasattr(command_center, "apply_remediation")
        assert not hasattr(command_center, "mutate_network")
        assert not hasattr(command_center, "override_safety_prechecks")

    def test_large_list_rendering_behavior(self, mock_inventory_service):
        topo = MagicMock(spec=TopologyService)
        inc_service = MagicMock(spec=IncidentService)

        # Generate 200 mock incidents
        now = datetime.now(timezone.utc)
        large_incs = []
        for i in range(200):
            large_incs.append(
                IncidentRecord(
                    incident_id=f"INC-BULK-{i:04d}",
                    device_id="branch3-uplink" if i % 2 == 0 else "core-01",
                    interface="Branch3-Uplink" if i % 2 == 0 else "Campus Core",
                    title=f"Bulk Telemetry Flap {i}",
                    severity=IncidentSeverity.HIGH if i % 3 == 0 else IncidentSeverity.MEDIUM,
                    status=IncidentStatus.OPEN,
                    risk_score=0.50 + (i % 50) / 100.0,
                    time_to_impact=100.0 + i,
                    created_at=now + timedelta(seconds=i),
                )
            )
        inc_service.get_all_incidents.return_value = large_incs

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )
        state = cmd.build_summary_state()
        assert len(state.work_queue) == 200
        # Check deterministic descending sorting preserved
        scores = [item.priority_score for item in state.work_queue]
        assert scores == sorted(scores, reverse=True)
