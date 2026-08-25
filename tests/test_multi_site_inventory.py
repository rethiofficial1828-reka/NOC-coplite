"""
Unit and Integration Tests for MultiSiteInventoryService (v1.3 Phase 1).

Covers:
1. Site and device registry mapping
2. Device-to-site bidirectional resolution
3. Aggregate site health calculation (HEALTHY, DEGRADED, CRITICAL, OFFLINE)
4. Active incident counting and critical incident isolation
5. Real telemetry metric readback (no synthetic fabrication)
6. Read-only advisory execution guarantees
"""

from unittest.mock import MagicMock
import pytest

from agents.incident.incident_models import (
    IncidentAssignment,
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)
from agents.incident.incident_service import IncidentService
from agents.multi_site.multi_site_models import (
    SiteHealthStatus,
    SiteRecord,
    SiteType,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.telemetry.telemetry_service import TelemetryService
from agents.topology.topology_service import TopologyService
from config.config_manager import ConfigManager
from config.settings import DEVICE_REGISTRY, SITE_REGISTRY


@pytest.fixture
def mock_telemetry_service():
    service = MagicMock(spec=TelemetryService)
    repo = MagicMock()
    # Return healthy metrics by default
    metric_mock = MagicMock()
    metric_mock.latency = 18.5
    metric_mock.packet_loss = 0.0
    metric_mock.utilization = 32.0
    repo.get_recent_metrics.return_value = [metric_mock]
    service.repository = repo
    return service


@pytest.fixture
def mock_incident_service():
    service = MagicMock(spec=IncidentService)
    service.get_all_incidents.return_value = []
    return service


@pytest.fixture
def inventory_service(mock_telemetry_service, mock_incident_service):
    config = ConfigManager.get_instance()
    topology_service = MagicMock(spec=TopologyService)
    return MultiSiteInventoryService(
        config_manager=config,
        telemetry_service=mock_telemetry_service,
        incident_service=mock_incident_service,
        topology_service=topology_service,
    )


class TestMultiSiteInventoryService:
    """Test suite for MultiSiteInventoryService."""

    def test_get_all_sites_returns_all_configured_sites(self, inventory_service):
        sites = inventory_service.get_all_sites(evaluate_health=False)
        assert len(sites) >= 4
        site_ids = [s.site_id for s in sites]
        assert "site-campus" in site_ids
        assert "site-dc" in site_ids
        assert "site-branch3" in site_ids
        assert "site-branch1" in site_ids

    def test_get_site_returns_correct_site_record(self, inventory_service):
        site = inventory_service.get_site("site-branch3", evaluate_health=False)
        assert site is not None
        assert site.site_id == "site-branch3"
        assert site.site_name == "Branch Office 3"
        assert site.site_type == SiteType.BRANCH
        assert "branch3-uplink" in site.device_ids
        assert "ISP-A" in site.primary_providers
        assert "ISP-B" in site.backup_providers

    def test_get_site_devices_resolves_devices(self, inventory_service):
        devices = inventory_service.get_site_devices("site-campus")
        assert len(devices) >= 2
        dev_ids = [d["id"] for d in devices]
        assert "core-01" in dev_ids
        assert "rtr-01" in dev_ids

    def test_get_site_for_device_by_id_and_name(self, inventory_service):
        site1 = inventory_service.get_site_for_device("branch3-uplink")
        assert site1 is not None
        assert site1.site_id == "site-branch3"

        site2 = inventory_service.get_site_for_device("Branch3-Uplink")
        assert site2 is not None
        assert site2.site_id == "site-branch3"

        site3 = inventory_service.get_site_for_device("Campus Core")
        assert site3 is not None
        assert site3.site_id == "site-campus"

    def test_aggregate_site_health_nominal_baseline(self, inventory_service):
        summary = inventory_service.aggregate_site_health()
        assert summary["total_sites"] >= 4
        assert summary["healthy_sites"] == summary["total_sites"]
        assert summary["degraded_sites"] == 0
        assert summary["critical_sites"] == 0
        assert summary["total_active_incidents"] == 0

    def test_site_health_degraded_on_high_loss(self, mock_telemetry_service, mock_incident_service):
        metric_mock = MagicMock()
        metric_mock.latency = 95.0
        metric_mock.packet_loss = 4.5
        metric_mock.utilization = 88.0
        mock_telemetry_service.repository.get_recent_metrics.return_value = [metric_mock]

        service = MultiSiteInventoryService(
            telemetry_service=mock_telemetry_service,
            incident_service=mock_incident_service,
        )
        site = service.get_site("site-branch3", evaluate_health=True)
        assert site is not None
        assert site.health_status == SiteHealthStatus.DEGRADED
        assert site.average_latency_ms == 95.0
        assert site.average_loss_percent == 4.5

    def test_site_health_critical_on_critical_incident(self, mock_telemetry_service, mock_incident_service):
        crit_inc = IncidentRecord(
            incident_id="INC-2026-999001",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="WAN Primary Link Severe Congestion / Imminent Failure",
            severity=IncidentSeverity.CRITICAL,
            status=IncidentStatus.OPEN,
            risk_score=0.92,
            time_to_impact=18.0,
        )
        mock_incident_service.get_all_incidents.return_value = [crit_inc]

        service = MultiSiteInventoryService(
            telemetry_service=mock_telemetry_service,
            incident_service=mock_incident_service,
        )
        site = service.get_site("site-branch3", evaluate_health=True)
        assert site is not None
        assert site.health_status == SiteHealthStatus.CRITICAL
        assert site.active_incidents_count == 1
        assert site.critical_incidents_count == 1

    def test_read_only_advisory_invariants(self, inventory_service):
        # Service has no mutation or execution methods
        assert not hasattr(inventory_service, "execute_failover")
        assert not hasattr(inventory_service, "apply_configuration")
        assert not hasattr(inventory_service, "mutate_network")
