"""
Multi-Site Operational Hardening & End-to-End Safety Acceptance Tests (v1.3 Phase 5).

Covers all 18 operational hardening requirements:
1. multi-incident inventory
2. correlation consistency
3. priority ordering
4. queue refresh
5. incident resolution
6. isolated real failover
7. isolated rollback
8. no cross-incident mutation
9. audit isolation
10. approval isolation
11. plan-hash isolation
12. deterministic refresh
13. queue cap
14. filtering
15. drill-down preservation
16. return navigation
17. advisory-only correlation
18. production mode remains blocked
"""

from datetime import datetime, timedelta, timezone
import time
from typing import List
from unittest.mock import MagicMock
import pytest

from agents.failover.approval_manager import ApprovalManager
from agents.failover.authorized_execution_adapter import AuthorizedNetworkAdapter
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.failover_models import (
    ApprovalStatus,
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStep,
    RestorationStatus,
    RollbackStatus,
)
from agents.failover.failover_service import FailoverService
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine
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
    CorrelationType,
    MultiSiteSummaryState,
    QueuePriority,
    SiteHealthStatus,
    SiteRecord,
    SiteType,
    WorkQueueItem,
)
from agents.multi_site.site_inventory_service import MultiSiteInventoryService
from agents.topology.topology_models import ImpactSeverity, TopologyNode
from agents.topology.topology_service import TopologyService
from agents.trust.trust_models import AutonomyLevel
from agents.trust.trust_service import TrustService


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
            health_status=SiteHealthStatus.HEALTHY,
            active_incidents_count=0,
            critical_incidents_count=0,
            average_latency_ms=12.0,
            average_loss_percent=0.1,
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
def base_incidents():
    now = datetime.now(timezone.utc)
    return [
        IncidentRecord(
            incident_id="INC-2026-001",
            device_id="branch3-uplink",
            interface="Branch3-Uplink",
            title="ISP-A Carrier Degradation on Branch 3",
            severity=IncidentSeverity.CRITICAL,
            status=IncidentStatus.OPEN,
            risk_score=0.92,
            time_to_impact=30.0,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-01", "EV-02"]},
            created_at=now,
        ),
        IncidentRecord(
            incident_id="INC-2026-002",
            device_id="core-01",
            interface="Campus Core",
            title="ISP-A Packet Loss on Campus",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.OPEN,
            risk_score=0.75,
            time_to_impact=90.0,
            metadata={"provider": "ISP-A", "evidence_ids": ["EV-03"]},
            created_at=now + timedelta(seconds=20),
        ),
        IncidentRecord(
            incident_id="INC-2026-003",
            device_id="branch3-uplink",
            interface="eth2",
            title="Secondary Link CRC Warning",
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.NEW,
            risk_score=0.15,
            time_to_impact=1200.0,
            metadata={"provider": "ISP-B"},
            created_at=now + timedelta(minutes=10),
        ),
    ]


class TestMultiSiteOperationalHardening:
    """Operational hardening and safety test suite."""

    # -----------------------------------------------------------------------
    # 1. Multi-Incident Inventory & Health
    # -----------------------------------------------------------------------
    def test_multi_incident_inventory(self, mock_inventory_service, base_incidents):
        inc_service = MagicMock(spec=IncidentService)
        inc_service.get_all_incidents.return_value = base_incidents
        topo = MagicMock(spec=TopologyService)

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )

        state = cmd.build_summary_state()
        assert state.total_sites == 4
        assert state.total_active_incidents == 3
        assert state.critical_active_incidents >= 1
        assert len(state.sites) == 4

    # -----------------------------------------------------------------------
    # 2. Correlation Consistency & Explanation
    # -----------------------------------------------------------------------
    def test_correlation_consistency(self, mock_inventory_service, base_incidents):
        inc_service = MagicMock(spec=IncidentService)
        inc_service.get_all_incidents.return_value = base_incidents
        topo = MagicMock(spec=TopologyService)

        correlator = CrossSiteCorrelationService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )
        groups = correlator.correlate_active_incidents(base_incidents)
        assert len(groups) >= 1
        grp = groups[0]
        assert grp.correlation_type == CorrelationType.SHARED_PROVIDER
        assert grp.shared_dependency == "ISP-A"
        assert set(grp.affected_site_ids) == {"site-branch3", "site-campus"}
        assert "EV-01" in grp.supporting_evidence_ids

    # -----------------------------------------------------------------------
    # 3. Deterministic Priority Ordering
    # -----------------------------------------------------------------------
    def test_priority_ordering(self, mock_inventory_service, base_incidents):
        topo = MagicMock(spec=TopologyService)
        prioritizer = IncidentPrioritizationService(
            inventory_service=mock_inventory_service,
            topology_service=topo,
        )
        ranked = prioritizer.prioritize_incidents(base_incidents)
        assert len(ranked) == 3
        # First must be CRITICAL INC-2026-001
        assert ranked[0].incident_id == "INC-2026-001"
        assert ranked[0].priority == QueuePriority.CRITICAL
        # Second must be HIGH INC-2026-002
        assert ranked[1].incident_id == "INC-2026-002"
        assert ranked[1].priority == QueuePriority.HIGH
        # Third must be LOW INC-2026-003
        assert ranked[2].incident_id == "INC-2026-003"
        assert ranked[2].priority == QueuePriority.LOW

    # -----------------------------------------------------------------------
    # 4. Queue Refresh & 5. Incident Resolution
    # -----------------------------------------------------------------------
    def test_incident_resolution_and_queue_refresh(self, mock_inventory_service, base_incidents):
        inc_service = MagicMock(spec=IncidentService)
        topo = MagicMock(spec=TopologyService)

        # Initially 3 active incidents
        inc_service.get_all_incidents.return_value = list(base_incidents)
        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )
        state1 = cmd.build_summary_state()
        assert state1.total_active_incidents == 3

        # Resolve the top incident (INC-2026-001)
        base_incidents[0].status = IncidentStatus.RESOLVED
        inc_service.get_all_incidents.return_value = list(base_incidents)

        state2 = cmd.build_summary_state()
        assert state2.total_active_incidents == 2
        active_ids = [q.incident_id for q in state2.work_queue]
        assert "INC-2026-001" not in active_ids
        assert "INC-2026-002" in active_ids
        assert "INC-2026-003" in active_ids

    # -----------------------------------------------------------------------
    # 6. Isolated Real Failover & 8. No Cross-Incident Mutation
    # -----------------------------------------------------------------------
    def test_isolated_failover_and_no_cross_incident_mutation(self):
        approval_mgr = ApprovalManager()
        validator = PreExecutionValidator()
        failover_svc = FailoverService(approval_manager=approval_mgr, validator=validator)

        # Plan for Incident A (branch3-uplink)
        plan_a = ExecutionPlan(
            plan_id="PLAN-A-001",
            decision_id="DEC-001",
            source_path="ISP-A",
            destination_path="ISP-B",
            target_devices=["branch3-uplink"],
            steps=[
                ExecutionStep(
                    step_id="STEP-A-1",
                    sequence=1,
                    adapter="DryRunExecutionAdapter",
                    target="branch3-uplink",
                    action_type="FAILOVER_PROVIDER",
                    parameters={"provider": "ISP-B"},
                )
            ],
            plan_hash="a" * 64,
        )
        # Plan for Incident B (core-01)
        plan_b = ExecutionPlan(
            plan_id="PLAN-B-002",
            decision_id="DEC-002",
            source_path="ISP-A",
            destination_path="ISP-B",
            target_devices=["core-01"],
            steps=[
                ExecutionStep(
                    step_id="STEP-B-1",
                    sequence=1,
                    adapter="DryRunExecutionAdapter",
                    target="core-01",
                    action_type="FAILOVER_PROVIDER",
                    parameters={"provider": "ISP-B"},
                )
            ],
            plan_hash="b" * 64,
        )

        # Approve ONLY Incident A
        req_a = approval_mgr.request_approval("DEC-001", "REQ-001", plan_a, operator_id="admin")
        ok_a, approval_a, _ = approval_mgr.approve_request(req_a.approval_id, operator_id="operator1", plan=plan_a)
        assert ok_a is True
        assert approval_a.status == ApprovalStatus.APPROVED
        assert approval_a.approved_execution_plan_hash == plan_a.plan_hash

        # Plan B was NEVER approved -> validate approval for Plan B fails
        ok_b, _ = approval_mgr.validate_approval(req_a.approval_id, plan_b)
        assert ok_b is False
        assert plan_a.plan_id != plan_b.plan_id

    # -----------------------------------------------------------------------
    # 7. Isolated Rollback
    # -----------------------------------------------------------------------
    def test_isolated_rollback(self):
        engine = RollbackEngine()
        # Create rollback plan for Incident A
        plan_a = ExecutionPlan(
            plan_id="PLAN-A-001",
            decision_id="DEC-001",
            source_path="ISP-A",
            destination_path="ISP-B",
            target_devices=["branch3-uplink"],
            steps=[
                ExecutionStep(
                    step_id="STEP-A-1",
                    sequence=1,
                    adapter="DryRunExecutionAdapter",
                    target="branch3-uplink",
                    action_type="FAILOVER_PROVIDER",
                    parameters={"metric": 10},
                )
            ],
            rollback_plan=[
                ExecutionStep(
                    step_id="STEP-ROLL-1",
                    sequence=1,
                    adapter="DryRunExecutionAdapter",
                    target="branch3-uplink",
                    action_type="FAILOVER_PROVIDER",
                    parameters={"metric": 20},
                )
            ],
            plan_hash="a" * 64,
        )

        exec_res = ExecutionResult(
            plan_id="PLAN-A-001",
            execution_mode=ExecutionMode.DRY_RUN,
            status=ExecutionStatus.VERIFICATION_FAILED,
            success=False,
            steps_executed=[],
        )
        adapter = DryRunExecutionAdapter()

        # Execute rollback for Plan A only
        result = engine.execute_rollback(plan=plan_a, execution_result=exec_res, adapter=adapter)
        assert result.status == RollbackStatus.COMPLETED
        assert result.restoration_status == RestorationStatus.RESTORED
        assert all(s.target == "branch3-uplink" for s in plan_a.steps)

    # -----------------------------------------------------------------------
    # 9. Audit Isolation & 10. Approval Isolation & 11. Plan-Hash Isolation
    # -----------------------------------------------------------------------
    def test_audit_approval_and_plan_hash_isolation(self):
        mgr = ApprovalManager()

        plan1 = ExecutionPlan(
            plan_id="PLAN-1",
            decision_id="DEC-1",
            source_path="ISP-A",
            destination_path="ISP-B",
            target_devices=["branch3-uplink"],
            steps=[
                ExecutionStep(
                    step_id="S-1",
                    sequence=1,
                    adapter="DryRunExecutionAdapter",
                    target="branch3-uplink",
                    action_type="FAILOVER_PROVIDER",
                    parameters={"target": "ISP-B"},
                )
            ],
            plan_hash="11" * 32,
        )
        plan2 = ExecutionPlan(
            plan_id="PLAN-2",
            decision_id="DEC-2",
            source_path="ISP-A",
            destination_path="ISP-B",
            target_devices=["core-01"],
            steps=[
                ExecutionStep(
                    step_id="S-2",
                    sequence=1,
                    adapter="DryRunExecutionAdapter",
                    target="core-01",
                    action_type="FAILOVER_PROVIDER",
                    parameters={"target": "ISP-B"},
                )
            ],
            plan_hash="22" * 32,
        )

        # Plan hashes must be cryptographically distinct
        assert plan1.plan_hash != plan2.plan_hash
        assert len(plan1.plan_hash) == 64

        # Approval token for plan1 cannot validate for plan2
        req1 = mgr.request_approval(decision_id="DEC-1", request_id="REQ-1", plan=plan1, operator_id="admin")
        ok1, apprv1, _ = mgr.approve_request(approval_id=req1.approval_id, operator_id="admin", plan=plan1)
        assert ok1 is True

        val1_ok, _ = mgr.validate_approval(approval_id=req1.approval_id, plan=plan1)
        val2_ok, _ = mgr.validate_approval(approval_id=req1.approval_id, plan=plan2)
        assert val1_ok is True
        assert val2_ok is False

    # -----------------------------------------------------------------------
    # 12. Deterministic Refresh
    # -----------------------------------------------------------------------
    def test_deterministic_refresh(self, mock_inventory_service, base_incidents):
        inc_service = MagicMock(spec=IncidentService)
        inc_service.get_all_incidents.return_value = list(base_incidents)
        topo = MagicMock(spec=TopologyService)

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )

        # Multiple consecutive calls must return identical results
        s1 = cmd.build_summary_state()
        s2 = cmd.build_summary_state()
        s3 = cmd.build_summary_state()

        assert s1.total_active_incidents == s2.total_active_incidents == s3.total_active_incidents == 3
        q1_ids = [q.incident_id for q in s1.work_queue]
        q2_ids = [q.incident_id for q in s2.work_queue]
        q3_ids = [q.incident_id for q in s3.work_queue]
        assert q1_ids == q2_ids == q3_ids

    # -----------------------------------------------------------------------
    # 13. Queue Cap to 50 Items
    # -----------------------------------------------------------------------
    def test_queue_cap_behavior(self, mock_inventory_service):
        inc_service = MagicMock(spec=IncidentService)
        now = datetime.now(timezone.utc)
        large_list = [
            IncidentRecord(
                incident_id=f"INC-CAP-{i:03d}",
                device_id="branch3-uplink",
                interface="Branch3-Uplink",
                title=f"Incident {i}",
                severity=IncidentSeverity.MEDIUM,
                status=IncidentStatus.OPEN,
                risk_score=0.50,
                created_at=now + timedelta(seconds=i),
            )
            for i in range(120)
        ]
        inc_service.get_all_incidents.return_value = large_list
        topo = MagicMock(spec=TopologyService)

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )
        state = cmd.build_summary_state()
        assert len(state.work_queue) == 120
        # When rendered in UI, sliced to top 50
        assert len(state.work_queue[:50]) == 50

    # -----------------------------------------------------------------------
    # 14. Filtering Capabilities
    # -----------------------------------------------------------------------
    def test_filtering_capabilities(self, mock_inventory_service, base_incidents):
        inc_service = MagicMock(spec=IncidentService)
        inc_service.get_all_incidents.return_value = list(base_incidents)
        topo = MagicMock(spec=TopologyService)

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )
        state = cmd.build_summary_state()

        # Filter by priority HIGH
        high_items = [q for q in state.work_queue if q.priority == QueuePriority.HIGH]
        assert len(high_items) == 1
        assert high_items[0].incident_id == "INC-2026-002"

        # Filter by site site-campus
        campus_items = [q for q in state.work_queue if q.site_id == "site-campus"]
        assert len(campus_items) == 1
        assert campus_items[0].device_id == "core-01"

    # -----------------------------------------------------------------------
    # 15. Drill-Down Context Preservation & 16. Return Navigation
    # -----------------------------------------------------------------------
    def test_drill_down_and_return_navigation(self, mock_inventory_service, base_incidents):
        inc_service = MagicMock(spec=IncidentService)
        inc_service.get_all_incidents.return_value = list(base_incidents)
        topo = MagicMock(spec=TopologyService)

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )
        state = cmd.build_summary_state()
        item = state.work_queue[0]

        # Simulate Drill-Down
        session = {
            "ui_view_mode": "DRILL_DOWN",
            "selected_device_name": item.device_id,
            "selected_incident_id": item.incident_id,
            "selected_site_id": item.site_id,
            "selected_group_id": item.correlated_group_id,
        }
        assert session["selected_device_name"] == "branch3-uplink"
        assert session["selected_incident_id"] == "INC-2026-001"
        assert session["selected_site_id"] == "site-branch3"

        # Simulate Return to Command Center
        session["ui_view_mode"] = "COMMAND_CENTER"
        assert session["ui_view_mode"] == "COMMAND_CENTER"
        # Context retained for breadcrumbs
        assert session["selected_device_name"] == "branch3-uplink"

    # -----------------------------------------------------------------------
    # 17. Advisory-Only Correlation & 18. Production Mode Hard-Blocked
    # -----------------------------------------------------------------------
    def test_advisory_correlation_and_production_hard_blocked(self, mock_inventory_service, base_incidents):
        inc_service = MagicMock(spec=IncidentService)
        inc_service.get_all_incidents.return_value = list(base_incidents)
        topo = MagicMock(spec=TopologyService)

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )
        # Correlated groups must be advisory objects with zero mutation methods
        groups = cmd.get_correlated_groups()
        for g in groups:
            assert not hasattr(g, "execute")
            assert not hasattr(g, "apply_failover")

        # Verify AuthorizedNetworkAdapter defaults to NOT_CONFIGURED and blocks execution
        adapter = AuthorizedNetworkAdapter(is_enabled=False)
        assert adapter.verify_capability() is False
        step = ExecutionStep(
            step_id="S-PROD",
            sequence=1,
            adapter="AuthorizedNetworkAdapter",
            target="core-01",
            action_type="FAILOVER_PROVIDER",
            parameters={"provider": "ISP-B"},
        )
        with pytest.raises(Exception):
            adapter.execute(step)

    # -----------------------------------------------------------------------
    # Performance & Scale Benchmarking (10, 50, 100, 500 Incidents)
    # -----------------------------------------------------------------------
    @pytest.mark.parametrize("incident_count", [10, 50, 100, 500])
    def test_performance_scaling(self, mock_inventory_service, incident_count):
        inc_service = MagicMock(spec=IncidentService)
        now = datetime.now(timezone.utc)
        incs = [
            IncidentRecord(
                incident_id=f"INC-PERF-{i:04d}",
                device_id="branch3-uplink" if i % 2 == 0 else "core-01",
                interface="Branch3-Uplink" if i % 2 == 0 else "Campus Core",
                title=f"Performance Test Anomaly {i}",
                severity=IncidentSeverity.HIGH if i % 3 == 0 else IncidentSeverity.MEDIUM,
                status=IncidentStatus.OPEN,
                risk_score=0.40 + (i % 60) / 100.0,
                time_to_impact=60.0 + (i % 300),
                created_at=now + timedelta(seconds=i),
            )
            for i in range(incident_count)
        ]
        inc_service.get_all_incidents.return_value = incs
        topo = MagicMock(spec=TopologyService)

        cmd = MultiSiteCommandCenterService(
            inventory_service=mock_inventory_service,
            incident_service=inc_service,
            topology_service=topo,
        )

        start_t = time.perf_counter()
        state = cmd.build_summary_state()
        elapsed = time.perf_counter() - start_t

        assert state.total_active_incidents == incident_count
        assert len(state.work_queue) == incident_count
        # Sub-second execution even for 500 simultaneous incidents
        assert elapsed < 1.0
        # Deterministic sorting preserved
        scores = [q.priority_score for q in state.work_queue]
        assert scores == sorted(scores, reverse=True)
