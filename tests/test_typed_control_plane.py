"""
Test Suite for NOC-Copilot v1.2 Phase 2: Typed Network Control-Plane Abstraction.

Comprehensive unit and integration tests verifying:
1. DRY_RUN execution remains unchanged and non-mutating.
2. LAB_AUTHORIZED without a configured driver is rejected cleanly at precheck.
3. LAB_AUTHORIZED with NotConfiguredControlPlane cannot mutate state.
4. Arbitrary command strings (shell injections, metacharacters) are strictly rejected.
5. Arbitrary SSH, subprocess, or CLI execution paths are unavailable in the architecture.
6. Typed action parameters strictly enforce Pydantic domain models.
7. Target and parameter validation logic prevents invalid executions.
8. PRODUCTION_AUTHORIZED mode is permanently blocked and raises ProductionExecutionDisabledError.
9. Readiness and health reporting accurately reflects NOT_CONFIGURED status.
10. Deterministic failure behavior and SQLite audit trail integrity.
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock

from pydantic import ValidationError

from agents.core.exceptions import ExecutionError
from agents.events.event_bus import EventBus
from agents.failover.approval_manager import ApprovalManager
from agents.failover.authorized_execution_adapter import AuthorizedNetworkAdapter
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.execution_adapter import IExecutionAdapter, INetworkProviderDelegate
from agents.failover.failover_models import (
    ApprovalStatus,
    ControlPlaneNotConfiguredError,
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    ExecutionRisk,
    ExecutionStatus,
    ExecutionStep,
    FailoverApproval,
    FailoverResult,
    PreExecutionCheck,
    ProductionExecutionDisabledError,
    RollbackStatus,
    UnauthorizedTargetError,
    VerificationStatus,
)
from agents.failover.failover_service import FailoverService
from agents.failover.network_control_plane import (
    ControlPlaneDriverType,
    ControlPlaneResponse,
    ControlPlaneStatus,
    FailbackProviderRequest,
    FailoverProviderRequest,
    INetworkControlPlane,
    NotConfiguredControlPlane,
    PathStateRequest,
    RouteVerificationRequest,
    SwitchInterfaceRequest,
    TypedControlPlaneDelegate,
)
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine
from agents.path_decision.path_models import (
    CandidatePath,
    DecisionStatus,
    FailoverRecommendation,
    PathDecisionResult,
    PathEvaluation,
    PathScore,
)


class MockHealthyControlPlane(INetworkControlPlane):
    """Mock operational control plane for testing typed dispatch."""

    def __init__(self) -> None:
        self.executed_actions = []

    @property
    def driver_type(self) -> ControlPlaneDriverType:
        return ControlPlaneDriverType.CUSTOM

    @property
    def is_configured(self) -> bool:
        return True

    def check_readiness(self) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="CHECK_READINESS",
            message="Mock control plane is ready.",
        )

    def failover_provider(self, request: FailoverProviderRequest) -> ControlPlaneResponse:
        self.executed_actions.append(("FAILOVER_PROVIDER", request))
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="FAILOVER_PROVIDER",
            target=request.target_device,
            message=f"Failover to {request.target_provider} completed.",
            details={"active_provider": request.target_provider},
        )

    def failback_provider(self, request: FailbackProviderRequest) -> ControlPlaneResponse:
        self.executed_actions.append(("FAILBACK_PROVIDER", request))
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="FAILBACK_PROVIDER",
            target=request.target_device,
            message=f"Failback to {request.target_provider} completed.",
            details={"active_provider": request.target_provider},
        )

    def switch_interface(self, request: SwitchInterfaceRequest) -> ControlPlaneResponse:
        self.executed_actions.append(("SWITCH_INTERFACE", request))
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="SWITCH_INTERFACE",
            target=request.target_device,
        )

    def enable_backup_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        self.executed_actions.append(("ENABLE_BACKUP_PATH", request))
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="ENABLE_BACKUP_PATH",
            target=request.target_device,
        )

    def disable_degraded_path(self, request: PathStateRequest) -> ControlPlaneResponse:
        self.executed_actions.append(("DISABLE_DEGRADED_PATH", request))
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="DISABLE_DEGRADED_PATH",
            target=request.target_device,
        )

    def verify_route_path(self, request: RouteVerificationRequest) -> ControlPlaneResponse:
        return ControlPlaneResponse(
            success=True,
            status=ControlPlaneStatus.READY,
            driver_type=self.driver_type,
            action_type="VERIFY_ROUTE_PATH",
            target=request.target_device,
        )


class TestTypedControlPlaneAbstraction(unittest.TestCase):
    """Test suite for typed network control-plane abstraction."""

    def setUp(self) -> None:
        self.event_bus = EventBus()
        self.approval_mgr = ApprovalManager()
        self.validator = PreExecutionValidator(approval_manager=self.approval_mgr)
        self.verifier = PostExecutionVerifier()
        self.rollback_engine = RollbackEngine()
        self.dry_run_adapter = DryRunExecutionAdapter()
        self.authorized_adapter = AuthorizedNetworkAdapter()
        self.failover_service = FailoverService(
            approval_manager=self.approval_mgr,
            validator=self.validator,
            verifier=self.verifier,
            rollback_engine=self.rollback_engine,
            dry_run_adapter=self.dry_run_adapter,
            authorized_adapter=self.authorized_adapter,
            event_bus=self.event_bus,
        )

    def _mock_decision(self) -> PathDecisionResult:
        cand1 = CandidatePath(path_id="P1", provider_name="ISP-A", wan_interface="Branch3-Uplink", source_device="Branch3-Uplink")
        cand2 = CandidatePath(path_id="P2", provider_name="ISP-B", wan_interface="Branch3-Backup", source_device="Branch3-Uplink")
        eval1 = PathEvaluation(candidate_id="P1", health=30.0, failure_risk=0.92)
        eval2 = PathEvaluation(candidate_id="P2", health=95.0, failure_risk=0.08)
        score1 = PathScore(candidate_id="P1", total_score=28.0)
        score2 = PathScore(candidate_id="P2", total_score=94.0)
        rec = FailoverRecommendation(
            current_provider="ISP-A",
            recommended_provider="ISP-B",
            decision_status=DecisionStatus.HUMAN_APPROVAL_REQUIRED,
        )
        return PathDecisionResult(
            request_id="REQ-TEST",
            candidate_paths=[cand1, cand2],
            evaluations=[eval1, eval2],
            scores=[score2, score1],
            recommendation=rec,
            current_path=cand1,
        )

    # -----------------------------------------------------------------------
    # Test 1: DRY_RUN mode unchanged
    # -----------------------------------------------------------------------
    def test_dry_run_mode_unchanged(self) -> None:
        """Verify DRY_RUN mode continues to execute simulated failover successfully."""
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.DRY_RUN,
            auto_approve=True,
            adapter_name="DryRunExecutionAdapter",
        )
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)
        self.assertIsNotNone(res.execution_result)
        self.assertEqual(res.execution_result.mode, ExecutionMode.DRY_RUN)
        self.assertEqual(res.execution_result.status, ExecutionStatus.EXECUTED)

    # -----------------------------------------------------------------------
    # Test 2: LAB_AUTHORIZED without configured driver is rejected cleanly
    # -----------------------------------------------------------------------
    def test_lab_authorized_without_driver_rejected_cleanly(self) -> None:
        """Verify LAB_AUTHORIZED with unconfigured AuthorizedNetworkAdapter halts at precheck."""
        # Unconfigured adapter by default has is_enabled=False, provider_delegate=None
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
        )
        self.assertEqual(res.final_status, ExecutionStatus.PRECHECK_FAILED)
        # Prechecks must record failure for adapter check (Check #14)
        adapter_check = next((c for c in res.prechecks if "Adapter" in c.check_name), None)
        self.assertIsNotNone(adapter_check)
        self.assertEqual(adapter_check.status, "FAILED")

    # -----------------------------------------------------------------------
    # Test 3: NotConfiguredControlPlane cannot mutate state
    # -----------------------------------------------------------------------
    def test_not_configured_control_plane_cannot_mutate_state(self) -> None:
        """Verify NotConfiguredControlPlane explicitly reports NOT_CONFIGURED and rejects calls."""
        cp = NotConfiguredControlPlane()
        self.assertFalse(cp.is_configured)
        self.assertEqual(cp.driver_type, ControlPlaneDriverType.NONE)

        # Readiness probe must report NOT_CONFIGURED
        readiness = cp.check_readiness()
        self.assertFalse(readiness.success)
        self.assertEqual(readiness.status, ControlPlaneStatus.NOT_CONFIGURED)

        # Mutation attempts must report NOT_CONFIGURED cleanly
        req = FailoverProviderRequest(
            target_device="Branch3-Uplink",
            wan_interface="Branch3-Uplink",
            source_provider="ISP-A",
            target_provider="ISP-B",
        )
        resp = cp.failover_provider(req)
        self.assertFalse(resp.success)
        self.assertEqual(resp.status, ControlPlaneStatus.NOT_CONFIGURED)
        self.assertIn("No network control plane driver is configured", resp.message)

        # Delegate wrapping NotConfiguredControlPlane must report is_ready = False
        delegate = TypedControlPlaneDelegate(control_plane=cp)
        self.assertFalse(delegate.is_ready())
        self.assertFalse(delegate.verify_capability())

    # -----------------------------------------------------------------------
    # Test 4: Arbitrary command strings are rejected
    # -----------------------------------------------------------------------
    def test_arbitrary_command_strings_rejected(self) -> None:
        """Verify adapter rejects targets and parameters containing shell syntax or command keys."""
        adapter = AuthorizedNetworkAdapter(is_enabled=True)

        # Target injection attempts
        for bad_target in ["; rm -rf /", "rtr-01 && sudo reboot", "rtr-01 | cat /etc/passwd", "`whoami`", "$(id)"]:
            self.assertFalse(adapter.validate_target(bad_target), f"Should reject target: {bad_target}")

        # Parameter key injection attempts
        self.assertFalse(adapter.validate_action("FAILOVER_PROVIDER", {"cmd": "reboot"}))
        self.assertFalse(adapter.validate_action("FAILOVER_PROVIDER", {"command": "ip route add"}))
        self.assertFalse(adapter.validate_action("FAILOVER_PROVIDER", {"shell": "sh"}))
        self.assertFalse(adapter.validate_action("FAILOVER_PROVIDER", {"exec": "vtysh"}))
        self.assertFalse(adapter.validate_action("FAILOVER_PROVIDER", {"script": "/tmp/failover.sh"}))
        self.assertFalse(adapter.validate_action("FAILOVER_PROVIDER", {"password": "admin"}))
        self.assertFalse(adapter.validate_action("FAILOVER_PROVIDER", {"private_key": "secret"}))

    # -----------------------------------------------------------------------
    # Test 5: Arbitrary SSH/subprocess paths are unavailable
    # -----------------------------------------------------------------------
    def test_arbitrary_ssh_and_subprocess_paths_unavailable(self) -> None:
        """Verify the control plane classes do not expose generic shell or SSH execution methods."""
        cp = NotConfiguredControlPlane()
        self.assertFalse(hasattr(cp, "run_shell"))
        self.assertFalse(hasattr(cp, "exec_command"))
        self.assertFalse(hasattr(cp, "ssh_connect"))
        self.assertFalse(hasattr(cp, "subprocess"))

        delegate = TypedControlPlaneDelegate(control_plane=cp)
        self.assertFalse(hasattr(delegate, "run_shell"))
        self.assertFalse(hasattr(delegate, "exec_command"))
        self.assertFalse(hasattr(delegate, "execute_shell"))

    # -----------------------------------------------------------------------
    # Test 6: Typed action parameter validation
    # -----------------------------------------------------------------------
    def test_typed_action_parameter_validation(self) -> None:
        """Verify Pydantic models enforce typed parameters and reject malformed schemas."""
        # Valid request
        req = FailoverProviderRequest(
            target_device="Branch3-Uplink",
            wan_interface="Branch3-Uplink",
            source_provider="ISP-A",
            target_provider="ISP-B",
            next_hop="172.20.20.11",
        )
        self.assertEqual(req.target_provider, "ISP-B")
        self.assertEqual(req.next_hop, "172.20.20.11")

        # Missing required field must raise validation error
        with self.assertRaises(ValidationError):
            FailoverProviderRequest(target_device="Branch3-Uplink")  # type: ignore

        with self.assertRaises(ValidationError):
            SwitchInterfaceRequest(target_device="rtr-01")  # type: ignore

    # -----------------------------------------------------------------------
    # Test 7: Target allowlist and validation logic
    # -----------------------------------------------------------------------
    def test_target_allowlist_enforced(self) -> None:
        """Verify AuthorizedNetworkAdapter validates target syntax."""
        adapter = AuthorizedNetworkAdapter(is_enabled=True)
        self.assertTrue(adapter.validate_target("Branch3-Uplink"))
        self.assertTrue(adapter.validate_target("core-01"))
        self.assertTrue(adapter.validate_target("fw-01"))
        self.assertTrue(adapter.validate_target("rtr-01"))

        # Empty or non-string targets rejected
        self.assertFalse(adapter.validate_target(""))
        self.assertFalse(adapter.validate_target(None))  # type: ignore

    # -----------------------------------------------------------------------
    # Test 8: PRODUCTION_AUTHORIZED mode is permanently blocked
    # -----------------------------------------------------------------------
    def test_production_mode_remains_permanently_blocked(self) -> None:
        """Verify ExecutionMode.PRODUCTION_AUTHORIZED unconditionally raises ProductionExecutionDisabledError."""
        with self.assertRaises(ProductionExecutionDisabledError):
            self.failover_service.execute_failover_pipeline(
                target_interface_or_device="Branch3-Uplink",
                execution_mode=ExecutionMode.PRODUCTION_AUTHORIZED,
                auto_approve=True,
            )

    # -----------------------------------------------------------------------
    # Test 9: Readiness and health reporting
    # -----------------------------------------------------------------------
    def test_readiness_and_health_reporting(self) -> None:
        """Verify readiness and capability probes accurately distinguish between configured and unconfigured."""
        # Unconfigured
        unconfigured_cp = NotConfiguredControlPlane()
        unconfigured_del = TypedControlPlaneDelegate(control_plane=unconfigured_cp)
        unconfigured_adapter = AuthorizedNetworkAdapter(is_enabled=True, provider_delegate=unconfigured_del)
        self.assertFalse(unconfigured_adapter.verify_capability())

        # Configured Mock
        mock_cp = MockHealthyControlPlane()
        mock_del = TypedControlPlaneDelegate(control_plane=mock_cp)
        mock_adapter = AuthorizedNetworkAdapter(is_enabled=True, provider_delegate=mock_del)
        self.assertTrue(mock_adapter.verify_capability())
        self.assertTrue(mock_del.is_ready())

    # -----------------------------------------------------------------------
    # Test 10: Deterministic failure behavior and audit trail
    # -----------------------------------------------------------------------
    def test_deterministic_failure_behavior_and_audit(self) -> None:
        """Verify that an unconfigured LAB_AUTHORIZED execution creates complete audit records."""
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.LAB_AUTHORIZED,
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
        )
        self.assertEqual(res.final_status, ExecutionStatus.PRECHECK_FAILED)
        self.assertTrue(res.audit_reference.startswith("AUDIT-"))

    # -----------------------------------------------------------------------
    # Test 11: Typed action dispatch through delegate
    # -----------------------------------------------------------------------
    def test_typed_action_dispatch_through_delegate(self) -> None:
        """Verify TypedControlPlaneDelegate successfully translates steps to typed requests."""
        mock_cp = MockHealthyControlPlane()
        delegate = TypedControlPlaneDelegate(control_plane=mock_cp)

        # 1. Failover
        res = delegate.execute_typed_action(
            action_type="FAILOVER_PROVIDER",
            target="Branch3-Uplink",
            parameters={"source_provider": "ISP-A", "target_provider": "ISP-B", "interface": "Branch3-Uplink"},
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["action_type"], "FAILOVER_PROVIDER")
        self.assertEqual(len(mock_cp.executed_actions), 1)
        action_name, req_obj = mock_cp.executed_actions[0]
        self.assertEqual(action_name, "FAILOVER_PROVIDER")
        self.assertIsInstance(req_obj, FailoverProviderRequest)
        self.assertEqual(req_obj.target_provider, "ISP-B")

        # 2. Rollback
        res_rb = delegate.rollback_typed_action(
            action_type="FAILOVER_PROVIDER",
            target="Branch3-Uplink",
            parameters={"source_provider": "ISP-A", "target_provider": "ISP-B", "interface": "Branch3-Uplink"},
        )
        self.assertTrue(res_rb["success"])
        self.assertEqual(len(mock_cp.executed_actions), 2)
        rb_action, rb_req = mock_cp.executed_actions[1]
        self.assertEqual(rb_action, "FAILBACK_PROVIDER")
        self.assertIsInstance(rb_req, FailbackProviderRequest)
        self.assertEqual(rb_req.target_provider, "ISP-A")


if __name__ == "__main__":
    unittest.main()
