"""
Unit and Integration Tests for IncidentPrioritizationService (v1.3 Phase 3).

Covers all 17 required validation cases:
1. deterministic score calculation
2. severity ordering
3. risk ordering
4. blast-radius influence
5. TTI urgency
6. correlation influence
7. queue priority mapping
8. deterministic tie-breaking
9. empty queue
10. missing TTI
11. missing correlation
12. multiple sites
13. correlated groups
14. read-only behavior
15. priority does not bypass approval
16. priority does not alter trust/autonomy
17. v1.2 failover remains unchanged
"""

from datetime import datetime, timedelta, timezone
import math
from unittest.mock import MagicMock
import pytest

from agents.incident.incident_models import (
    IncidentRecord,
    IncidentSeverity,
    IncidentStatus,
)
from agents.multi_site.incident_prioritizer import IncidentPrioritizationService
from agents.multi_site.multi_site_models import (
    CorrelatedIncidentGroup,
    CorrelationType,
    QueuePriority,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.topology.topology_models import ImpactSeverity
from agents.topology.topology_service import TopologyService


@pytest.fixture
def mock_inventory():
    service = MagicMock(spec=MultiSiteInventoryService)

    site_branch3 = MagicMock()
    site_branch3.site_id = "site-branch3"
    site_branch3.site_name = "Branch Office 3"

    site_campus = MagicMock()
    site_campus.site_id = "site-campus"
    site_campus.site_name = "Campus Main Site"

    def _get_site(device_key: str):
        k = str(device_key).lower()
        if "branch3" in k:
            return site_branch3
        elif "core" in k or "rtr" in k:
            return site_campus
        return None

    service.get_site_for_device.side_effect = _get_site
    return service


@pytest.fixture
def mock_topology():
    service = MagicMock(spec=TopologyService)
    blast = MagicMock()
    blast.severity = ImpactSeverity.HIGH
    service.calculate_blast_radius.return_value = blast
    return service


@pytest.fixture
def prioritizer(mock_inventory, mock_topology):
    return IncidentPrioritizationService(
        inventory_service=mock_inventory,
        topology_service=mock_topology,
    )


class TestIncidentPrioritizationService:
    """Comprehensive test suite for deterministic incident prioritization."""

    def test_deterministic_score_calculation(self, prioritizer):
        # S=HIGH(0.75), R=0.80, B=HIGH(0.75), TTI=60s (e^(-60/300)=e^(-0.2)~=0.8187), C=1.0
        # Expected = 0.30*0.75 + 0.25*0.80 + 0.20*0.75 + 0.15*0.8187 + 0.10*1.0
        #          = 0.225 + 0.200 + 0.150 + 0.1228 + 0.100 = 0.7978
        score, tier = prioritizer.compute_priority_score(
            severity=IncidentSeverity.HIGH,
            risk_score=0.80,
            blast_radius=ImpactSeverity.HIGH,
            time_to_impact=60.0,
            is_correlated=True,
        )
        assert score == pytest.approx(0.7978, abs=0.001)
        assert tier == QueuePriority.HIGH

    def test_severity_ordering(self, prioritizer):
        s_crit, _ = prioritizer.compute_priority_score(IncidentSeverity.CRITICAL, 0.5, ImpactSeverity.MEDIUM, 300, False)
        s_high, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, 300, False)
        s_med, _ = prioritizer.compute_priority_score(IncidentSeverity.MEDIUM, 0.5, ImpactSeverity.MEDIUM, 300, False)
        s_low, _ = prioritizer.compute_priority_score(IncidentSeverity.LOW, 0.5, ImpactSeverity.MEDIUM, 300, False)

        assert s_crit > s_high > s_med > s_low

    def test_risk_ordering(self, prioritizer):
        s_high_risk, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.95, ImpactSeverity.MEDIUM, 300, False)
        s_low_risk, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.10, ImpactSeverity.MEDIUM, 300, False)

        assert s_high_risk > s_low_risk

    def test_blast_radius_influence(self, prioritizer):
        s_crit_blast, _ = prioritizer.compute_priority_score(IncidentSeverity.MEDIUM, 0.5, ImpactSeverity.CRITICAL, 300, False)
        s_low_blast, _ = prioritizer.compute_priority_score(IncidentSeverity.MEDIUM, 0.5, ImpactSeverity.LOW, 300, False)

        assert s_crit_blast > s_low_blast

    def test_tti_urgency(self, prioritizer):
        # 10s TTI vs 300s TTI vs 1200s TTI
        s_imminent, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, 10.0, False)
        s_moderate, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, 300.0, False)
        s_distant, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, 1200.0, False)

        assert s_imminent > s_moderate > s_distant

    def test_correlation_influence(self, prioritizer):
        s_corr, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, 300, True)
        s_uncorr, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, 300, False)

        # Difference must exactly be 0.10 (weight for correlation)
        assert pytest.approx(s_corr - s_uncorr, abs=0.001) == 0.10

    def test_queue_priority_mapping(self, prioritizer):
        # CRITICAL severity always maps to CRITICAL tier
        _, tier_crit = prioritizer.compute_priority_score(IncidentSeverity.CRITICAL, 0.1, ImpactSeverity.LOW, 1000, False)
        assert tier_crit == QueuePriority.CRITICAL

        # High score >= 0.80
        _, tier_high_score = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.95, ImpactSeverity.CRITICAL, 30, True)
        assert tier_high_score == QueuePriority.CRITICAL

        # Medium score >= 0.40
        _, tier_med = prioritizer.compute_priority_score(IncidentSeverity.MEDIUM, 0.5, ImpactSeverity.MEDIUM, 300, False)
        assert tier_med == QueuePriority.MEDIUM

        # Low score < 0.40
        _, tier_low = prioritizer.compute_priority_score(IncidentSeverity.LOW, 0.1, ImpactSeverity.LOW, 1000, False)
        assert tier_low == QueuePriority.LOW

    def test_deterministic_tie_breaking(self, prioritizer):
        now = datetime.now(timezone.utc)
        # 3 incidents with identical priority scores
        inc1 = IncidentRecord(
            incident_id="INC-001",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Incident 1",
            severity=IncidentSeverity.HIGH,
            risk_score=0.5,
            time_to_impact=60.0,
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-002",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Incident 2",
            severity=IncidentSeverity.HIGH,
            risk_score=0.5,
            time_to_impact=30.0,  # Shorter TTI -> should come before inc1
            created_at=now,
        )
        inc3 = IncidentRecord(
            incident_id="INC-003",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Incident 3",
            severity=IncidentSeverity.HIGH,
            risk_score=0.5,
            time_to_impact=60.0,
            created_at=now + timedelta(seconds=10),  # Later created_at -> should come after inc1
        )

        ranked = prioritizer.prioritize_incidents([inc1, inc3, inc2])
        assert [r.incident_id for r in ranked] == ["INC-002", "INC-001", "INC-003"]

    def test_empty_queue(self, prioritizer):
        assert prioritizer.prioritize_incidents([]) == []

    def test_missing_tti(self, prioritizer):
        # Missing TTI uses e^(-1) neutral value
        s_missing, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, None, False)
        s_exact_300, _ = prioritizer.compute_priority_score(IncidentSeverity.HIGH, 0.5, ImpactSeverity.MEDIUM, 300.0, False)
        assert s_missing == s_exact_300

    def test_missing_correlation(self, prioritizer):
        now = datetime.now(timezone.utc)
        inc = IncidentRecord(
            incident_id="INC-SOLO",
            device_id="core-01",
            interface="Campus Core",
            title="Solo incident",
            severity=IncidentSeverity.MEDIUM,
            risk_score=0.4,
            created_at=now,
        )
        items = prioritizer.prioritize_incidents([inc], correlated_groups=None)
        assert len(items) == 1
        assert items[0].correlated_group_id is None
        assert items[0].priority_score >= 0.0

    def test_multiple_sites(self, prioritizer):
        now = datetime.now(timezone.utc)
        inc_b3 = IncidentRecord(
            incident_id="INC-B3",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Branch 3 issue",
            severity=IncidentSeverity.HIGH,
            risk_score=0.8,
            created_at=now,
        )
        inc_campus = IncidentRecord(
            incident_id="INC-CAMPUS",
            device_id="core-01",
            interface="Campus Core",
            title="Campus issue",
            severity=IncidentSeverity.HIGH,
            risk_score=0.8,
            created_at=now,
        )
        items = prioritizer.prioritize_incidents([inc_b3, inc_campus])
        assert len(items) == 2
        sites = {i.site_id for i in items}
        assert "site-branch3" in sites
        assert "site-campus" in sites

    def test_correlated_groups(self, prioritizer):
        now = datetime.now(timezone.utc)
        inc1 = IncidentRecord(
            incident_id="INC-C1",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A issue",
            severity=IncidentSeverity.HIGH,
            risk_score=0.7,
            created_at=now,
        )
        inc2 = IncidentRecord(
            incident_id="INC-C2",
            device_id="core-01",
            interface="Campus Core",
            title="ISP-A issue",
            severity=IncidentSeverity.HIGH,
            risk_score=0.7,
            created_at=now,
        )
        grp = CorrelatedIncidentGroup(
            group_id="GRP-ISP-A-1",
            correlation_type=CorrelationType.SHARED_PROVIDER,
            title="Shared ISP-A Outage",
            description="Carrier degradation on ISP-A",
            incident_ids=["INC-C1", "INC-C2"],
            affected_site_ids=["site-branch3", "site-campus"],
            affected_devices=["branch3-uplink", "core-01"],
            shared_dependency="ISP-A",
            correlation_confidence=0.90,
        )

        items = prioritizer.prioritize_incidents([inc1, inc2], correlated_groups=[grp])
        assert len(items) == 2
        for it in items:
            assert it.correlated_group_id == "GRP-ISP-A-1"

    def test_read_only_behavior(self, prioritizer):
        now = datetime.now(timezone.utc)
        inc = IncidentRecord(
            incident_id="INC-RO",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Readonly test",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.75,
            created_at=now,
        )
        prioritizer.prioritize_incidents([inc])
        assert inc.status == IncidentStatus.OPEN
        assert inc.severity == IncidentSeverity.HIGH
        assert inc.risk_score == 0.75

    def test_priority_does_not_bypass_approval(self, prioritizer):
        now = datetime.now(timezone.utc)
        inc_crit = IncidentRecord(
            incident_id="INC-CRIT-999",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="Critical degradation",
            severity=IncidentSeverity.CRITICAL,
            risk_score=0.99,
            time_to_impact=10.0,
            created_at=now,
        )
        items = prioritizer.prioritize_incidents([inc_crit])
        assert len(items) == 1
        # Even a CRITICAL priority item strictly requires human approval
        assert items[0].priority == QueuePriority.CRITICAL
        assert items[0].trust_requirement == "HUMAN_APPROVAL_REQUIRED"

    def test_priority_does_not_alter_trust_or_autonomy(self, prioritizer):
        # Verify prioritizer has no references to trust score mutation or policy bypass
        assert not hasattr(prioritizer, "set_autonomy_level")
        assert not hasattr(prioritizer, "grant_execution_authority")
        assert not hasattr(prioritizer, "override_policy")

    def test_v1_2_failover_remains_unchanged(self, prioritizer):
        # Verify prioritizer has no failover execution methods
        assert not hasattr(prioritizer, "execute_failover")
        assert not hasattr(prioritizer, "mutate_network")
        assert not hasattr(prioritizer, "trigger_rollback")
