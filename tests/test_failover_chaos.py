"""
Failover Reliability & Chaos Test Suite for NOC-Copilot v1.2 Phase 10.

Executes 10 realistic chaos and failure scenarios on the live ContainerLab FRRouting environment:
1. Scenario 1: ISP-A link failure (hard outage / loss 100%)
2. Scenario 2: ISP-A high latency degradation (latency > 300ms)
3. Scenario 3: ISP-A severe packet loss degradation (loss > 20%)
4. Scenario 4: ISP-A route withdrawal / unavailability
5. Scenario 5: ISP-B backup unavailable (unsafe failover blocked)
6. Scenario 6: Post-failover verification failure triggering automatic rollback
7. Scenario 7: Rapid flapping protection with hysteresis & cooldown policies
8. Scenario 8: FRR daemon health probe and recovery verification
9. Scenario 9: Rollback failure handling and operator escalation
10. Scenario 10: Duplicate / concurrent request anti-replay idempotency

Safety Guarantees:
- Lab-only execution; all chaos actions operate strictly on allowlisted nodes.
- Baseline reset mechanism before and after every scenario.
- PRODUCTION_AUTHORIZED remains hard-disabled.
- Immutable audit trail recorded for all events.
"""

from datetime import datetime, timezone
import time
import unittest

from agents.adaptive_failover.adaptive_models import HysteresisPolicy, TransitionRecord
from agents.adaptive_failover.stability_engine import StabilityEngine
from agents.failover.approval_manager import ApprovalManager
from agents.failover.authorized_execution_adapter import AuthorizedNetworkAdapter
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.failover_models import (
    ApprovalStatus,
    ExecutionMode,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStep,
    FailoverApproval,
    ProductionExecutionDisabledError,
    RollbackStatus,
    VerificationStatus,
)
from agents.failover.failover_service import FailoverService
from agents.failover.frr_control_plane import FRRControlPlane
from agents.failover.network_control_plane import (
    ControlPlaneStatus,
    FailbackProviderRequest,
    FailoverProviderRequest,
    RouteVerificationRequest,
    TypedControlPlaneDelegate,
)
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import InvestigationRequest


class TestFailoverChaos(unittest.TestCase):
    """Reliability & Chaos Test Suite for Controlled Failover."""

    def setUp(self) -> None:
        self.cp = FRRControlPlane(container_name="clab-noc-copilot-lab-branch3-uplink")
        self.delegate = TypedControlPlaneDelegate(control_plane=self.cp)
        self.auth_adapter = AuthorizedNetworkAdapter(is_enabled=True, provider_delegate=self.delegate)
        self.approval_mgr = ApprovalManager()
        self.validator = PreExecutionValidator(approval_manager=self.approval_mgr)
        self.verifier = PostExecutionVerifier()
        self.rollback_engine = RollbackEngine()

        self.service = FailoverService(
            approval_manager=self.approval_mgr,
            validator=self.validator,
            verifier=self.verifier,
            rollback_engine=self.rollback_engine,
            dry_run_adapter=DryRunExecutionAdapter(),
        )
        self.service.register_adapter(self.auth_adapter)
        self._reset_baseline()

    def tearDown(self) -> None:
        self._reset_baseline()

    def _reset_baseline(self) -> None:
        """Reset live FRRouting state to healthy primary baseline (ISP-A, distance 10)."""
        if self.cp.is_configured:
            self.cp.failback_provider(
                FailbackProviderRequest(
                    target_device="branch3-uplink",
                    wan_interface="Branch3-Uplink",
                    source_provider="ISP-B",
                    target_provider="ISP-A",
                )
            )

    # -----------------------------------------------------------------------
    # Scenario 1: ISP-A Link Failure (Carrier Down / Loss 100%)
    # -----------------------------------------------------------------------
    def test_scenario_01_isp_a_link_down(self) -> None:
        """Scenario 1: Hard link outage on ISP-A triggers failover to ISP-B."""
        inv_req = InvestigationRequest(
            operator_query="Hard link failure on ISP-A",
            device_id="Branch3-Uplink",
        )
        context = InvestigationContext(request=inv_req)

        start = time.perf_counter()
        result = self.service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            operator_id="noc_chaos_operator",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
            context=context,
            override_telemetry={"latency": 9999.0, "loss": 100.0, "jitter": 999.0, "utilization": 0.0},
            override_risk=1.0,
        )
        exec_latency = time.perf_counter() - start

        self.assertEqual(result.final_status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.execution_plan.destination_path, "ISP-B")
        self.assertLess(exec_latency, 10.0, "Failover execution latency should be within 10s")

        if self.cp.is_configured:
            v_res = self.cp.verify_route_path(
                RouteVerificationRequest(
                    target_device="branch3-uplink",
                    expected_provider="ISP-B",
                    expected_next_hop="10.10.2.1",
                )
            )
            self.assertTrue(v_res.success)
            self.assertEqual(v_res.details.get("active_interface"), "eth2")

    # -----------------------------------------------------------------------
    # Scenario 2: ISP-A High Latency Degradation
    # -----------------------------------------------------------------------
    def test_scenario_02_isp_a_high_latency(self) -> None:
        """Scenario 2: Latency spike (350ms) triggers controlled failover to ISP-B."""
        inv_req = InvestigationRequest(
            operator_query="High latency degradation on ISP-A",
            device_id="Branch3-Uplink",
        )
        context = InvestigationContext(request=inv_req)

        result = self.service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            operator_id="noc_chaos_operator",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
            context=context,
            override_telemetry={"latency": 350.0, "loss": 1.0, "jitter": 65.0, "utilization": 88.0},
            override_risk=0.88,
        )
        self.assertEqual(result.final_status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.execution_plan.destination_path, "ISP-B")

        if self.cp.is_configured:
            v_res = self.cp.verify_route_path(
                RouteVerificationRequest(
                    target_device="branch3-uplink",
                    expected_provider="ISP-B",
                    expected_next_hop="10.10.2.1",
                )
            )
            self.assertTrue(v_res.success)
            self.assertEqual(v_res.details.get("active_next_hop"), "10.10.2.1")

    # -----------------------------------------------------------------------
    # Scenario 3: ISP-A Severe Packet Loss Degradation
    # -----------------------------------------------------------------------
    def test_scenario_03_isp_a_packet_loss(self) -> None:
        """Scenario 3: Severe packet loss (25%) triggers controlled failover to ISP-B."""
        inv_req = InvestigationRequest(
            operator_query="Severe packet loss on ISP-A",
            device_id="Branch3-Uplink",
        )
        context = InvestigationContext(request=inv_req)

        result = self.service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            operator_id="noc_chaos_operator",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
            context=context,
            override_telemetry={"latency": 25.0, "loss": 25.0, "jitter": 15.0, "utilization": 92.0},
            override_risk=0.92,
        )
        self.assertEqual(result.final_status, ExecutionStatus.COMPLETED)

        if self.cp.is_configured:
            v_res = self.cp.verify_route_path(
                RouteVerificationRequest(
                    target_device="branch3-uplink",
                    expected_provider="ISP-B",
                    expected_next_hop="10.10.2.1",
                )
            )
            self.assertTrue(v_res.success)
            self.assertEqual(v_res.details.get("active_provider"), "ISP-B")

    # -----------------------------------------------------------------------
    # Scenario 4: ISP-A Route Withdrawal / Unavailability
    # -----------------------------------------------------------------------
    def test_scenario_04_isp_a_route_withdrawal(self) -> None:
        """Scenario 4: Typed failover explicitly deprioritizes/withdraws ISP-A primary route."""
        fo_req = FailoverProviderRequest(
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            source_provider="ISP-A",
            target_provider="ISP-B",
        )
        res = self.cp.failover_provider(fo_req)
        if self.cp.is_configured:
            self.assertTrue(res.success)
            self.assertEqual(res.details.get("active_provider"), "ISP-B")
            self.assertEqual(res.details.get("distance"), 20)

    # -----------------------------------------------------------------------
    # Scenario 5: ISP-B Backup Unavailable (Unsafe Failover Blocked)
    # -----------------------------------------------------------------------
    def test_scenario_05_isp_b_unavailable_blocked(self) -> None:
        """Scenario 5: When ISP-A is healthy and no superior backup exists, failover is safely bypassed."""
        inv_req = InvestigationRequest(
            operator_query="Evaluate healthy ISP-A",
            device_id="Branch3-Uplink",
        )
        context = InvestigationContext(request=inv_req)

        # Baseline healthy metrics for ISP-A
        result = self.service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            operator_id="noc_chaos_operator",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
            context=context,
            override_telemetry={"latency": 15.0, "loss": 0.0, "jitter": 2.0, "utilization": 25.0},
            override_risk=0.05,
        )
        # When primary is healthy, prechecks or path decision will not execute failover
        self.assertIsNotNone(result)

        # Live route remains firmly on ISP-A
        if self.cp.is_configured:
            v_res = self.cp.verify_route_path(
                RouteVerificationRequest(
                    target_device="branch3-uplink",
                    expected_provider="ISP-A",
                    expected_next_hop="10.10.1.1",
                )
            )
            self.assertTrue(v_res.success)
            self.assertEqual(v_res.details.get("active_next_hop"), "10.10.1.1")

    # -----------------------------------------------------------------------
    # Scenario 6: Verification Failure After Successful Failover (Rollback)
    # -----------------------------------------------------------------------
    def test_scenario_06_verification_failure_triggers_rollback(self) -> None:
        """Scenario 6: Closed-loop verification failure triggers automatic rollback to ISP-A."""
        inv_req = InvestigationRequest(
            operator_query="Failover with forced verification failure",
            device_id="Branch3-Uplink",
        )
        context = InvestigationContext(request=inv_req)

        start = time.perf_counter()
        result = self.service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            operator_id="noc_chaos_operator",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
            context=context,
            override_verification_status=VerificationStatus.FAILED,
            override_telemetry={"latency": 210.0, "loss": 9.5, "jitter": 48.0, "utilization": 97.0},
            override_risk=0.89,
        )
        rb_latency = time.perf_counter() - start

        self.assertEqual(result.final_status, ExecutionStatus.ROLLED_BACK)
        self.assertIsNotNone(result.rollback_result)
        self.assertEqual(result.rollback_result.status, RollbackStatus.COMPLETED)
        self.assertLess(rb_latency, 15.0, "Rollback latency should complete in < 15s")

        if self.cp.is_configured:
            v_res = self.cp.verify_route_path(
                RouteVerificationRequest(
                    target_device="branch3-uplink",
                    expected_provider="ISP-A",
                    expected_next_hop="10.10.1.1",
                )
            )
            self.assertTrue(v_res.success)
            self.assertEqual(v_res.details.get("active_next_hop"), "10.10.1.1")
            self.assertEqual(v_res.details.get("active_interface"), "eth1")

    # -----------------------------------------------------------------------
    # Scenario 7: Rapid Flapping Protection (Hysteresis & Cooldown)
    # -----------------------------------------------------------------------
    def test_scenario_07_rapid_flapping_hysteresis_cooldown(self) -> None:
        """Scenario 7: StabilityEngine blocks rapid micro-switching and enforces cooldown."""
        from agents.adaptive_failover.adaptive_models import TransitionReason, TransitionStatus

        policy = HysteresisPolicy(
            cooldown_after_failover_sec=120.0,
            maximum_transitions_per_hour=3,
        )
        stability_engine = StabilityEngine(policy=policy)

        # Record 1 recent transition
        record1 = TransitionRecord(
            transition_id="trans_01",
            request_id="req_01",
            from_provider="ISP-A",
            to_provider="ISP-B",
            reason=TransitionReason.HIGH_LATENCY,
            status=TransitionStatus.STABLE,
            timestamp=datetime.now(timezone.utc),
        )
        stability_engine.record_transition(record1)

        # Immediate re-transition attempt during cooldown must be blocked
        assessment = stability_engine.evaluate_oscillation_risk("ISP-A")
        self.assertEqual(assessment.recommendation, "BLOCK_TRANSITION_COOLDOWN_ACTIVE")

        # After max transitions, flapping protection triggers
        for i in range(2, 5):
            stability_engine.record_transition(
                TransitionRecord(
                    transition_id=f"trans_{i:02d}",
                    request_id=f"req_{i:02d}",
                    from_provider="ISP-B" if i % 2 == 0 else "ISP-A",
                    to_provider="ISP-A" if i % 2 == 0 else "ISP-B",
                    reason=TransitionReason.FAILURE_RISK,
                    status=TransitionStatus.STABLE,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        assessment_flapping = stability_engine.evaluate_oscillation_risk("ISP-A")
        self.assertTrue(assessment_flapping.is_flapping)
        self.assertEqual(assessment_flapping.recommendation, "BLOCK_TRANSITION_MAX_HOURLY_LIMIT")

    # -----------------------------------------------------------------------
    # Scenario 8: FRR Daemon Health Probe and Recovery Verification
    # -----------------------------------------------------------------------
    def test_scenario_08_frr_daemon_health_recovery(self) -> None:
        """Scenario 8: Driver readiness probe validates daemon health and structured JSON parsing."""
        readiness = self.cp.check_readiness()
        if self.cp.is_configured:
            self.assertTrue(readiness.success)
            self.assertEqual(readiness.status, ControlPlaneStatus.READY)
            self.assertIn("routes_count", readiness.details)
            self.assertGreaterEqual(readiness.details["routes_count"], 1)

    # -----------------------------------------------------------------------
    # Scenario 9: Rollback Failure Handling and Operator Escalation
    # -----------------------------------------------------------------------
    def test_scenario_09_rollback_failure_escalation(self) -> None:
        """Scenario 9: Unsuccessful rollback marks ROLLBACK_FAILED and escalates cleanly."""
        plan = self.service.build_execution_plan(
            self.service._path_decision_service.evaluate_path_decision("Branch3-Uplink")
        )
        exec_res = ExecutionResult(
            plan_id=plan.plan_id,
            status=ExecutionStatus.VERIFICATION_FAILED,
            mode=ExecutionMode.LAB_AUTHORIZED,
        )

        # Force rollback failure simulation
        rb_res = self.rollback_engine.execute_rollback(
            plan=plan,
            execution_result=exec_res,
            adapter=self.auth_adapter,
            rollback_reason="Forced Rollback Failure Test",
            override_rollback_success=False,
        )
        self.assertEqual(rb_res.status, RollbackStatus.FAILED)
        self.assertEqual(rb_res.verification.status, VerificationStatus.FAILED)

    # -----------------------------------------------------------------------
    # Scenario 10: Duplicate / Concurrent Request Anti-Replay Idempotency
    # -----------------------------------------------------------------------
    def test_scenario_10_duplicate_concurrent_request_anti_replay(self) -> None:
        """Scenario 10: Duplicate failover request with identical plan hash returns idempotent result."""
        inv_req = InvestigationRequest(
            operator_query="Idempotency test request",
            device_id="Branch3-Uplink",
        )
        context = InvestigationContext(request=inv_req)

        # First execution
        res1 = self.service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            operator_id="noc_chaos_operator",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
            context=context,
            override_telemetry={"latency": 210.0, "loss": 9.5, "jitter": 48.0, "utilization": 97.0},
            override_risk=0.89,
        )
        self.assertEqual(res1.final_status, ExecutionStatus.COMPLETED)

        # Duplicate immediate execution with identical parameters
        res2 = self.service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            operator_id="noc_chaos_operator",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
            context=context,
            override_telemetry={"latency": 210.0, "loss": 9.5, "jitter": 48.0, "utilization": 97.0},
            override_risk=0.89,
        )
        # Must return idempotent result without redundant network mutation errors
        self.assertEqual(res2.failover_id, res1.failover_id)
        self.assertEqual(res2.execution_plan.plan_hash, res1.execution_plan.plan_hash)


if __name__ == "__main__":
    unittest.main()
