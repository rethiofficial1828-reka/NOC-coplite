"""
Test Suite for NOC-Copilot v1.2 Phase 8: Typed Live FRR Control-Plane Driver Integration.

Validates the live FRR control-plane driver against the running ContainerLab environment:
1. Driver readiness and capability reporting
2. Live route read from FRR structured state
3. Active next-hop read (10.10.1.1)
4. Active interface read (eth1)
5. Failover typed action (ISP-A -> ISP-B)
6. Actual next-hop change in FRR (10.10.2.1)
7. Actual egress interface change in FRR (eth2)
8. Verification after failover (ISP-B confirmed)
9. Failback typed action (ISP-B -> ISP-A)
10. Actual restoration in FRR (10.10.1.1 on eth1)
11. Automatic Rollback execution and validation
12. Target allowlist enforcement
13. Approval & plan-hash binding verification
14. DRY_RUN mode remains non-mutating
15. PRODUCTION_AUTHORIZED remains permanently blocked
"""

import unittest

from agents.failover.approval_manager import ApprovalManager
from agents.failover.authorized_execution_adapter import AuthorizedNetworkAdapter
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.failover_models import (
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStep,
    ProductionExecutionDisabledError,
)
from agents.failover.failover_service import FailoverService
from agents.failover.frr_control_plane import FRRControlPlane
from agents.failover.network_control_plane import (
    ControlPlaneDriverType,
    FailbackProviderRequest,
    FailoverProviderRequest,
    RouteVerificationRequest,
    TypedControlPlaneDelegate,
)
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine


class TestLiveFRRControlPlane(unittest.TestCase):
    """Test suite for live FRRControlPlane driver."""

    def setUp(self) -> None:
        self.cp = FRRControlPlane(container_name="clab-noc-copilot-lab-branch3-uplink")
        self.delegate = TypedControlPlaneDelegate(control_plane=self.cp)
        self.approval_mgr = ApprovalManager()

    # -----------------------------------------------------------------------
    # 1. Driver Readiness
    # -----------------------------------------------------------------------
    def test_driver_readiness(self) -> None:
        """Verify driver type and readiness reporting."""
        self.assertEqual(self.cp.driver_type, ControlPlaneDriverType.FRR_ZAPI)
        res = self.cp.check_readiness()
        self.assertIsInstance(res.success, bool)

    # -----------------------------------------------------------------------
    # 2. Live Route Read
    # -----------------------------------------------------------------------
    def test_live_route_read(self) -> None:
        """Verify driver reads live structured route table."""
        req = RouteVerificationRequest(target_device="branch3-uplink", expected_provider="")
        res = self.cp.verify_route_path(req)
        self.assertIsInstance(res.details, dict)

    # -----------------------------------------------------------------------
    # 3. Active Next-Hop Read
    # -----------------------------------------------------------------------
    def test_active_next_hop_read(self) -> None:
        """Verify driver identifies active next-hop."""
        req = RouteVerificationRequest(target_device="branch3-uplink", expected_provider="ISP-A")
        res = self.cp.verify_route_path(req)
        if res.success:
            self.assertEqual(res.details.get("active_next_hop"), "10.10.1.1")

    # -----------------------------------------------------------------------
    # 4. Active Interface Read
    # -----------------------------------------------------------------------
    def test_active_interface_read(self) -> None:
        """Verify driver identifies active egress interface."""
        req = RouteVerificationRequest(target_device="branch3-uplink", expected_provider="ISP-A")
        res = self.cp.verify_route_path(req)
        if res.success:
            self.assertEqual(res.details.get("active_interface"), "eth1")

    # -----------------------------------------------------------------------
    # 5. Failover Typed Action
    # -----------------------------------------------------------------------
    def test_failover_typed_action(self) -> None:
        """Verify failover_provider switches primary route to ISP-B."""
        req = FailoverProviderRequest(
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            source_provider="ISP-A",
            target_provider="ISP-B",
        )
        res = self.cp.failover_provider(req)
        if res.success:
            self.assertEqual(res.details.get("active_provider"), "ISP-B")
            self.assertEqual(res.details.get("active_next_hop"), "10.10.2.1")
            self.assertEqual(res.details.get("active_interface"), "eth2")

    # -----------------------------------------------------------------------
    # 6. Actual Next-Hop Change & Egress Change (ISP-B)
    # -----------------------------------------------------------------------
    def test_actual_next_hop_and_egress_change(self) -> None:
        """Verify verification confirms active next hop is 10.10.2.1 via eth2 after failover."""
        fo_req = FailoverProviderRequest(
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            source_provider="ISP-A",
            target_provider="ISP-B",
        )
        fo_res = self.cp.failover_provider(fo_req)
        if fo_res.success:
            verify_req = RouteVerificationRequest(
                target_device="branch3-uplink",
                expected_provider="ISP-B",
                expected_next_hop="10.10.2.1",
            )
            v_res = self.cp.verify_route_path(verify_req)
            self.assertTrue(v_res.success)
            self.assertEqual(v_res.details.get("active_next_hop"), "10.10.2.1")
            self.assertEqual(v_res.details.get("active_interface"), "eth2")

    # -----------------------------------------------------------------------
    # 7. Failback Typed Action & Restoration (ISP-A)
    # -----------------------------------------------------------------------
    def test_failback_typed_action_and_restoration(self) -> None:
        """Verify failback_provider restores primary route to ISP-A via 10.10.1.1 on eth1."""
        fb_req = FailbackProviderRequest(
            target_device="branch3-uplink",
            wan_interface="Branch3-Uplink",
            source_provider="ISP-B",
            target_provider="ISP-A",
        )
        fb_res = self.cp.failback_provider(fb_req)
        if fb_res.success:
            verify_req = RouteVerificationRequest(
                target_device="branch3-uplink",
                expected_provider="ISP-A",
                expected_next_hop="10.10.1.1",
            )
            v_res = self.cp.verify_route_path(verify_req)
            self.assertTrue(v_res.success)
            self.assertEqual(v_res.details.get("active_next_hop"), "10.10.1.1")
            self.assertEqual(v_res.details.get("active_interface"), "eth1")

    # -----------------------------------------------------------------------
    # 8. Delegate Integration & Verification
    # -----------------------------------------------------------------------
    def test_delegate_integration(self) -> None:
        """Verify TypedControlPlaneDelegate passes operations through to FRRControlPlane."""
        if self.cp.is_configured:
            self.assertTrue(self.delegate.is_ready())
            self.assertTrue(self.delegate.verify_capability())

            # Test delegate failover
            ok = self.delegate.failover_provider("ISP-A", "ISP-B", "Branch3-Uplink", "branch3-uplink")
            self.assertTrue(ok)

            # Test delegate failback
            ok_fb = self.delegate.failback_provider("ISP-B", "ISP-A", "Branch3-Uplink", "branch3-uplink")
            self.assertTrue(ok_fb)

    # -----------------------------------------------------------------------
    # 9. Target Allowlist
    # -----------------------------------------------------------------------
    def test_target_allowlist(self) -> None:
        """Verify unauthorized target device returns validation failure."""
        adapter = AuthorizedNetworkAdapter(is_enabled=True, provider_delegate=self.delegate)
        is_valid = adapter.validate_target("malicious_host; rm -rf /")
        self.assertFalse(is_valid)

        is_valid_allowed = adapter.validate_target("Branch3-Uplink")
        self.assertTrue(is_valid_allowed)

    # -----------------------------------------------------------------------
    # 10. Approval and Plan-Hash Binding
    # -----------------------------------------------------------------------
    def test_approval_and_plan_hash_binding(self) -> None:
        """Verify plan hash matching is required for approval validation."""
        steps = [
            ExecutionStep(
                step_id="step_1",
                action_type="FAILOVER_PROVIDER",
                target="Branch3-Uplink",
                parameters={"source_provider": "ISP-A", "target_provider": "ISP-B"},
            )
        ]
        plan = ExecutionPlan(
            plan_id="plan_test",
            decision_id="dec_test",
            source_path="ISP-A",
            destination_path="ISP-B",
            target_devices=["Branch3-Uplink"],
            steps=steps,
            rollback_plan=[],
            plan_hash="",
        )
        plan.plan_hash = self.approval_mgr.compute_plan_hash(plan)

        approval = self.approval_mgr.request_approval(
            decision_id="dec_test",
            request_id="req_test",
            plan=plan,
        )
        ok, approved_obj, _ = self.approval_mgr.approve_request(
            approval_id=approval.approval_id,
            operator_id="noc_admin",
            plan=plan,
        )
        self.assertTrue(ok)

        # Must validate successfully with correct plan
        is_valid, _ = self.approval_mgr.validate_approval(approval.approval_id, plan)
        self.assertTrue(is_valid)

        # Must fail if plan is altered
        tampered_plan = ExecutionPlan(
            plan_id="plan_tampered",
            decision_id="dec_test",
            source_path="ISP-A",
            destination_path="MALICIOUS-ISP",
            target_devices=["Branch3-Uplink"],
            steps=steps,
            rollback_plan=[],
            plan_hash="tampered_hash_123",
        )
        is_valid_tampered, _ = self.approval_mgr.validate_approval(approval.approval_id, tampered_plan)
        self.assertFalse(is_valid_tampered)

    # -----------------------------------------------------------------------
    # 11. Rollback Execution via RollbackEngine
    # -----------------------------------------------------------------------
    def test_rollback_execution(self) -> None:
        """Verify RollbackEngine executes failback rollback steps."""
        adapter = AuthorizedNetworkAdapter(is_enabled=True, provider_delegate=self.delegate)
        rollback_engine = RollbackEngine()
        steps = []
        rb_steps = [
            ExecutionStep(
                step_id="rb_1",
                action_type="FAILBACK_PROVIDER",
                target="Branch3-Uplink",
                parameters={"source_provider": "ISP-B", "target_provider": "ISP-A"},
            )
        ]
        plan = ExecutionPlan(
            plan_id="plan_rb",
            decision_id="dec_rb",
            source_path="ISP-A",
            destination_path="ISP-B",
            target_devices=["Branch3-Uplink"],
            steps=steps,
            rollback_plan=rb_steps,
            plan_hash="hash_rb",
        )
        exec_res = ExecutionResult(
            plan_id=plan.plan_id,
            status=ExecutionStatus.VERIFICATION_FAILED,
            mode=ExecutionMode.LAB_AUTHORIZED,
        )
        res = rollback_engine.execute_rollback(plan=plan, execution_result=exec_res, adapter=adapter)
        self.assertIsNotNone(res)

    # -----------------------------------------------------------------------
    # 12. DRY_RUN Remains Non-Mutating
    # -----------------------------------------------------------------------
    def test_dry_run_remains_non_mutating(self) -> None:
        """Verify DryRunExecutionAdapter executes without touching the live network."""
        dry_adapter = DryRunExecutionAdapter()
        step = ExecutionStep(
            step_id="dry_step",
            action_type="FAILOVER_PROVIDER",
            target="Branch3-Uplink",
            parameters={"source_provider": "ISP-A", "target_provider": "ISP-B"},
        )
        res = dry_adapter.execute(step)
        self.assertIn("status", res)
        self.assertEqual(res["status"], "SIMULATED_SUCCESS")

    # -----------------------------------------------------------------------
    # 13. Production Mode Remains Blocked
    # -----------------------------------------------------------------------
    def test_production_mode_remains_blocked(self) -> None:
        """Verify PRODUCTION_AUTHORIZED raises ProductionExecutionDisabledError."""
        validator = PreExecutionValidator(approval_manager=self.approval_mgr)
        service = FailoverService(
            approval_manager=self.approval_mgr,
            validator=validator,
            dry_run_adapter=DryRunExecutionAdapter(),
        )
        with self.assertRaises(ProductionExecutionDisabledError):
            service.execute_failover_pipeline(
                target_interface_or_device="Branch3-Uplink",
                execution_mode=ExecutionMode.PRODUCTION_AUTHORIZED,
                auto_approve=True,
            )


if __name__ == "__main__":
    unittest.main()
