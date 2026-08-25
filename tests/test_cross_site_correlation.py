"""
Unit and Integration Tests for CrossSiteCorrelationService (v1.3 Phase 2).

Covers all 14 required validation cases:
1. shared provider correlation
2. shared topology dependency correlation
3. similar fingerprint correlation
4. synchronized temporal correlation
5. unrelated incidents remain separate
6. duplicate correlation elimination
7. evidence IDs preserved
8. contradicting evidence preserved
9. deterministic confidence calculation
10. empty incident set
11. missing/unresolved topology
12. missing historical fingerprint
13. read-only behavior
14. no failover/execution side effects
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
from agents.multi_site.cross_site_correlator import CrossSiteCorrelationService
from agents.multi_site.multi_site_models import (
    CorrelatedIncidentGroup,
    CorrelationType,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.orchestrator_ai.evidence_registry import EvidenceRegistry
from agents.premortem.incident_fingerprint import IncidentFingerprintEngine
from agents.topology.topology_models import TopologyNode
from agents.topology.topology_service import TopologyService


@pytest.fixture
def mock_inventory_service():
    service = MagicMock(spec=MultiSiteInventoryService)

    site_branch3 = MagicMock()
    site_branch3.site_id = "site-branch3"
    site_branch3.site_name = "Branch Office 3"
    site_branch3.primary_providers = ["ISP-A"]
    site_branch3.backup_providers = ["ISP-B"]

    site_branch1 = MagicMock()
    site_branch1.site_id = "site-branch1"
    site_branch1.site_name = "Branch Office 1"
    site_branch1.primary_providers = ["ISP-A"]
    site_branch1.backup_providers = ["ISP-B"]

    site_campus = MagicMock()
    site_campus.site_id = "site-campus"
    site_campus.site_name = "Campus Main Site"
    site_campus.primary_providers = ["ISP-A"]
    site_campus.backup_providers = ["ISP-B"]

    site_dc = MagicMock()
    site_dc.site_id = "site-dc"
    site_dc.site_name = "Data Center HQ"
    site_dc.primary_providers = ["ISP-B"]
    site_dc.backup_providers = ["ISP-A"]

    def _get_site(device_id_or_name: str):
        dev = str(device_id_or_name).lower()
        if "branch3" in dev:
            return site_branch3
        elif "branch1" in dev:
            return site_branch1
        elif "core" in dev or "rtr" in dev:
            return site_campus
        elif "fw" in dev or "hub" in dev:
            return site_dc
        return None

    service.get_site_for_device.side_effect = _get_site
    return service


@pytest.fixture
def mock_topology_service():
    service = MagicMock(spec=TopologyService)

    def _upstream(device_id: str):
        dev = str(device_id).lower()
        if "branch3" in dev or "branch1" in dev:
            node = MagicMock(spec=TopologyNode)
            node.node_id = "core-01"
            return [node]
        return []

    service.find_upstream_dependencies.side_effect = _upstream
    return service


@pytest.fixture
def correlator(mock_inventory_service, mock_topology_service):
    incident_service = MagicMock(spec=IncidentService)
    fingerprint_engine = IncidentFingerprintEngine()
    evidence_registry = EvidenceRegistry()

    return CrossSiteCorrelationService(
        inventory_service=mock_inventory_service,
        incident_service=incident_service,
        topology_service=mock_topology_service,
        fingerprint_engine=fingerprint_engine,
        evidence_registry=evidence_registry,
    )


class TestCrossSiteCorrelationService:
    """Complete validation suite for CrossSiteCorrelationService."""

    def test_shared_provider_correlation(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-001",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="WAN ISP-A Packet Loss & High Latency",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.82,
            time_to_impact=45.0,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-001", "EV-002"]},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-002",
            device_id="branch1",
            interface="branch1",
            title="WAN Primary ISP-A Carrier Jitter & Loss",
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.OPEN,
            risk_score=0.68,
            time_to_impact=120.0,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-003"]},
            created_at=now + timedelta(seconds=120),  # >60s to isolate provider rule
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert len(groups) >= 1
        grp = next(g for g in groups if g.correlation_type == CorrelationType.SHARED_PROVIDER)
        assert grp.shared_dependency == "ISP-A"
        assert set(grp.affected_site_ids) == {"site-branch3", "site-branch1"}
        assert set(grp.incident_ids) == {"INC-2026-001", "INC-2026-002"}
        assert "EV-001" in grp.supporting_evidence_ids
        assert "EV-003" in grp.supporting_evidence_ids
        assert grp.correlation_confidence >= 0.70

    def test_shared_topology_dependency_correlation(self, correlator):
        now = datetime.now(timezone.utc)
        # Incidents do not mention ISP-A (different providers) but share upstream core-01
        inc1 = IncidentRecord(
            incident_id="INC-2026-011",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Ingress Traffic Drop on Branch 3",
            incident_type="TRAFFIC_DROP",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.78,
            metadata={"provider": "ISP-X", "evidence_ids": ["EV-TOPO-1"]},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-012",
            device_id="branch1",
            interface="branch1",
            title="Ingress Queue Full on Branch 1",
            incident_type="QUEUE_FULL",
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.OPEN,
            risk_score=0.55,
            metadata={"provider": "ISP-Y", "evidence_ids": ["EV-TOPO-2"]},
            created_at=now + timedelta(seconds=300),  # > 60s
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert len(groups) >= 1
        grp = next(g for g in groups if g.correlation_type == CorrelationType.SHARED_TOPOLOGY_DEPENDENCY)
        assert grp.shared_dependency == "core-01"
        assert set(grp.affected_site_ids) == {"site-branch3", "site-branch1"}
        assert "EV-TOPO-1" in grp.supporting_evidence_ids
        assert grp.correlation_confidence >= 0.75

    def test_similar_fingerprint_correlation(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-021",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            incident_type="BGP_OSCILLATION",
            title="BGP Prefix Flapping on Branch 3",
            contributing_signals=["BGP_STATE_FLAP", "HOLD_TIMER_EXPIRED"],
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.75,
            metadata={"provider": "ISP-1", "evidence_ids": ["EV-SIG-1"]},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-022",
            device_id="core-01",
            interface="Campus Core",
            incident_type="BGP_OSCILLATION",
            title="BGP Prefix Flapping on Campus Core",
            contributing_signals=["BGP_STATE_FLAP", "HOLD_TIMER_EXPIRED"],
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.75,
            metadata={"provider": "ISP-2", "evidence_ids": ["EV-SIG-2"]},
            created_at=now + timedelta(seconds=200),
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert len(groups) >= 1
        grp = groups[0]
        assert "BGP_OSCILLATION" in grp.shared_dependency or "BGP_STATE_FLAP" in grp.shared_dependency
        assert set(grp.affected_site_ids) == {"site-branch3", "site-campus"}
        assert grp.correlation_confidence >= 0.80

    def test_synchronized_temporal_correlation(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-031",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Sudden Ingress Spike",
            incident_type="SPIKE_A",
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.OPEN,
            risk_score=0.60,
            metadata={"provider": "ISP-1", "evidence_ids": ["EV-TIME-1"]},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-032",
            device_id="core-01",
            interface="Campus Core",
            title="Sudden Ingress Spike on Core",
            incident_type="SPIKE_B",
            severity=IncidentSeverity.MEDIUM,
            status=IncidentStatus.OPEN,
            risk_score=0.60,
            metadata={"provider": "ISP-2", "evidence_ids": ["EV-TIME-2"]},
            created_at=now + timedelta(seconds=25),  # 25s apart (<= 60s)
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert len(groups) >= 1
        grp = next(g for g in groups if g.correlation_type == CorrelationType.SYNCHRONIZED_TEMPORAL)
        assert set(grp.affected_site_ids) == {"site-branch3", "site-campus"}
        assert set(grp.incident_ids) == {"INC-2026-031", "INC-2026-032"}
        assert "EV-TIME-1" in grp.supporting_evidence_ids

    def test_unrelated_incidents_remain_separate(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-041",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Local Port Physical CRC Error",
            incident_type="PORT_CRC_ERROR",
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.OPEN,
            risk_score=0.15,
            metadata={"provider": "ISP-LOCAL"},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-042",
            device_id="fw-01",
            interface="Firewall",
            title="Firewall Management High Memory",
            incident_type="MEM_THRESHOLD",
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.OPEN,
            risk_score=0.20,
            metadata={"provider": "ISP-MGMT"},
            created_at=now + timedelta(hours=2),  # 2 hours apart
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        # Distinct providers, distinct incident types, distinct topology branches, >60s apart -> No grouping
        assert len(groups) == 0

    def test_duplicate_correlation_elimination(self, correlator):
        now = datetime.now(timezone.utc)
        # Matching both SHARED_PROVIDER and SYNCHRONIZED_TEMPORAL
        inc1 = IncidentRecord(
            incident_id="INC-2026-051",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A Carrier Congestion",
            incident_type="WAN_CONGESTION",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.85,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-A1"]},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-052",
            device_id="branch1",
            interface="branch1",
            title="ISP-A Carrier Congestion",
            incident_type="WAN_CONGESTION",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.85,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-A2"]},
            created_at=now + timedelta(seconds=15),  # 15s apart
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        # Must be merged into a SINGLE deduplicated group
        assert len(groups) == 1
        grp = groups[0]
        assert grp.correlation_type == CorrelationType.SHARED_PROVIDER
        # Secondary correlation captured in secondary_correlation_types
        assert CorrelationType.SYNCHRONIZED_TEMPORAL in grp.secondary_correlation_types or CorrelationType.SIMILAR_FAILURE_SIGNATURE in grp.secondary_correlation_types
        assert set(grp.incident_ids) == {"INC-2026-051", "INC-2026-052"}

    def test_evidence_ids_preserved(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-061",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A Packet Loss",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            metadata={"provider": "ISP-A", "evidence_ids": ["EVID-TEL-9988", "EVID-PRED-1122"]},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-062",
            device_id="branch1",
            interface="branch1",
            title="ISP-A Packet Loss",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            metadata={"provider": "ISP-A", "evidence_ids": ["EVID-TEL-7766"]},
            created_at=now,
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert len(groups) == 1
        ev_ids = groups[0].supporting_evidence_ids
        assert "EVID-TEL-9988" in ev_ids
        assert "EVID-PRED-1122" in ev_ids
        assert "EVID-TEL-7766" in ev_ids

    def test_contradicting_evidence_preserved(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-071",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A Link Flapping",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            metadata={
                "provider": "ISP-A",
                "evidence_ids": ["EV-SUPP-1"],
                "contradicting_evidence_ids": ["EV-CONTRA-1"],
            },
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-072",
            device_id="branch1",
            interface="branch1",
            title="ISP-A Link Flapping",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            metadata={
                "provider": "ISP-A",
                "evidence_ids": ["EV-SUPP-2"],
                "contradicting_evidence_ids": ["EV-CONTRA-2"],
            },
            created_at=now,
        )

        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert len(groups) == 1
        grp = groups[0]
        assert "EV-CONTRA-1" in grp.contradicting_evidence_ids
        assert "EV-CONTRA-2" in grp.contradicting_evidence_ids
        # Confidence penalized by contradicting evidence
        assert grp.correlation_confidence < 0.90

    def test_deterministic_confidence_calculation(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-081",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A Packet Loss",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            metadata={"provider": "ISP-A", "evidence_ids": ["E1", "E2"]},
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-082",
            device_id="branch1",
            interface="branch1",
            title="ISP-A Packet Loss",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            metadata={"provider": "ISP-A", "evidence_ids": ["E3"]},
            created_at=now,
        )

        groups1 = correlator.correlate_active_incidents([inc1, inc2])
        groups2 = correlator.correlate_active_incidents([inc1, inc2])
        assert len(groups1) == len(groups2) == 1
        assert groups1[0].correlation_confidence == groups2[0].correlation_confidence
        assert 0.70 <= groups1[0].correlation_confidence <= 1.0

    def test_empty_and_single_incident_set(self, correlator):
        assert correlator.correlate_active_incidents([]) == []

        single_inc = IncidentRecord(
            incident_id="INC-2026-091",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Single Anomaly",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
        )
        assert correlator.correlate_active_incidents([single_inc]) == []

    def test_missing_unresolved_topology(self, mock_inventory_service):
        mock_topo = MagicMock(spec=TopologyService)
        mock_topo.find_upstream_dependencies.side_effect = Exception("Topology DB error")

        correlator = CrossSiteCorrelationService(
            inventory_service=mock_inventory_service,
            topology_service=mock_topo,
        )
        # Should not crash; gracefully handles empty/errored upstream topology
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-01", device_id="branch3-uplink", interface="Branch3-Uplink",
            title="Local issue", status=IncidentStatus.OPEN, created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-02", device_id="branch1", interface="branch1",
            title="Local issue", status=IncidentStatus.OPEN, created_at=now,
        )
        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert isinstance(groups, list)

    def test_missing_historical_fingerprint(self, mock_inventory_service, mock_topology_service):
        correlator = CrossSiteCorrelationService(
            inventory_service=mock_inventory_service,
            topology_service=mock_topology_service,
            fingerprint_engine=None,
        )
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-101", device_id="branch3-uplink", interface="Branch3-Uplink",
            title="Anomaly A", status=IncidentStatus.OPEN, created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-102", device_id="branch1", interface="branch1",
            title="Anomaly B", status=IncidentStatus.OPEN, created_at=now,
        )
        groups = correlator.correlate_active_incidents([inc1, inc2])
        assert isinstance(groups, list)

    def test_read_only_behavior(self, correlator):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-2026-111",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A Outage",
            severity=IncidentSeverity.CRITICAL,
            status=IncidentStatus.OPEN,
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-2026-112",
            device_id="branch1",
            interface="branch1",
            title="ISP-A Outage",
            severity=IncidentSeverity.CRITICAL,
            status=IncidentStatus.OPEN,
            created_at=now,
        )

        correlator.correlate_active_incidents([inc1, inc2])
        # Verify incident status, severity, and attributes remain unaltered
        assert inc1.status == IncidentStatus.OPEN
        assert inc1.severity == IncidentSeverity.CRITICAL
        assert inc2.status == IncidentStatus.OPEN
        assert inc2.severity == IncidentSeverity.CRITICAL

    def test_no_failover_execution_side_effects(self, correlator):
        # Service has zero mutation or failover invocation capabilities
        assert not hasattr(correlator, "execute_failover")
        assert not hasattr(correlator, "apply_remediation")
        assert not hasattr(correlator, "trigger_route_change")
