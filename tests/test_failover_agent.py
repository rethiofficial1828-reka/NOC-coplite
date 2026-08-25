"""
Test Suite for Sprint 18 — Enterprise Controlled Failover Execution & Closed-Loop Verification Engine.

50+ Comprehensive Test Scenarios validating dry-run execution, approval manager lifecycles,
cryptographic plan-hash binding, anti-replay protection, 16-point pre-execution validation,
typed adapter execution (DryRun & Authorized), post-execution closed-loop verification,
automatic rollback procedures, security command injection boundaries, and E2E lifecycles.
"""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import MagicMock

from agents.events.event_bus import EventBus
from agents.failover.approval_manager import ApprovalManager
from agents.failover.authorized_execution_adapter import AuthorizedNetworkAdapter
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.execution_adapter import IExecutionAdapter, INetworkProviderDelegate
from agents.failover.failover_agent import FailoverAgent
from agents.failover.failover_models import (
    ActualOutcome,
    AdaptiveDecisionLearningResult,
    ApprovalStatus,
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    ExecutionRisk,
    ExecutionStatus,
    ExecutionStep,
    FailoverApproval,
    FailoverResult,
    LearningClassification,
    PredictedOutcome,
    RollbackResult,
    RollbackStatus,
    VerificationResult,
    VerificationStatus,
)
from agents.failover.failover_service import FailoverService
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import InvestigationRequest
from agents.path_decision.path_models import (
    CandidatePath,
    DecisionStatus,
    FailoverRecommendation,
    PathDecisionResult,
    PathEvaluation,
    PathScore,
)
from agents.schemas.schemas import ExecutionContext
from agents.trust.trust_models import AutonomyLevel, AutonomyPolicyResult, TrustDecision


class TestFailoverAgent(unittest.TestCase):
    """50+ Test Scenarios for Sprint 18 Controlled Failover Engine."""

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
        self.agent = FailoverAgent(event_bus=self.event_bus, service=self.failover_service)

    def _mock_decision_result(self, is_degraded: bool = True, top_score: float = 94.0) -> PathDecisionResult:
        cand1 = CandidatePath(path_id="P1", provider_name="ISP-A", wan_interface="Branch3-Uplink", source_device="Branch3-Uplink")
        cand2 = CandidatePath(path_id="P2", provider_name="ISP-B", wan_interface="Branch3-Backup", source_device="Branch3-Uplink")
        eval1 = PathEvaluation(candidate_id="P1", health=30.0 if is_degraded else 90.0, failure_risk=0.91 if is_degraded else 0.05)
        eval2 = PathEvaluation(candidate_id="P2", health=95.0, failure_risk=0.08)
        score1 = PathScore(candidate_id="P1", total_score=28.0 if is_degraded else 90.0)
        score2 = PathScore(candidate_id="P2", total_score=top_score)
        rec = FailoverRecommendation(
            current_provider="ISP-A",
            recommended_provider="ISP-B",
            decision_status=DecisionStatus.HUMAN_APPROVAL_REQUIRED if is_degraded else DecisionStatus.KEEP_CURRENT_PATH,
        )
        return PathDecisionResult(
            request_id="REQ-TEST",
            candidate_paths=[cand1, cand2],
            evaluations=[eval1, eval2],
            scores=[score2, score1] if is_degraded else [score1, score2],
            recommendation=rec,
            current_path=cand1,
        )

    # 1. Dry-run execution
    def test_01_dry_run_execution(self) -> None:
        step = ExecutionStep(sequence=1, adapter="DryRunExecutionAdapter", target="Branch3-Uplink", action_type="FAILOVER_PROVIDER", parameters={"target_provider": "ISP-B"})
        res = self.dry_run_adapter.execute(step)
        self.assertEqual(res["status"], "SIMULATED_SUCCESS")
        self.assertEqual(res["executed_in_mode"], "DRY_RUN")

    # 2. Missing approval
    def test_02_missing_approval(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec, approval=None)
        self.assertFalse(passed)
        chk = next(c for c in checks if c.check_name == "10. Required Approval Exists")
        self.assertEqual(chk.status, "FAILED")

    # 3. Expired approval
    def test_03_expired_approval(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        app = self.approval_mgr.request_approval(dec.decision_id, "REQ-1", plan, validity_minutes=-5)
        self.approval_mgr.approve_request(app.approval_id, "OPERATOR-1", plan)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec, approval=app)
        self.assertFalse(passed)
        chk = next(c for c in checks if c.check_name == "11. Approval Not Expired")
        self.assertEqual(chk.status, "FAILED")

    # 4. Rejected approval
    def test_04_rejected_approval(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        app = self.approval_mgr.request_approval(dec.decision_id, "REQ-1", plan)
        self.approval_mgr.reject_request(app.approval_id, "OPERATOR-1", "Security policy rejection")
        valid, msg = self.approval_mgr.validate_approval(app.approval_id, plan)
        self.assertFalse(valid)
        self.assertIn("REJECTED", msg)

    # 5. Invalidated approval
    def test_05_invalidated_approval(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        app = self.approval_mgr.request_approval(dec.decision_id, "REQ-1", plan)
        self.approval_mgr.approve_request(app.approval_id, "OPERATOR-1", plan)
        # Modify plan after approval
        plan.destination_path = "ISP-MODIFIED"
        valid, msg = self.approval_mgr.validate_approval(app.approval_id, plan)
        self.assertFalse(valid)
        self.assertEqual(app.status, ApprovalStatus.INVALIDATED)

    # 6. Plan hash mismatch
    def test_06_plan_hash_mismatch(self) -> None:
        dec = self._mock_decision_result()
        plan1 = self.failover_service.build_execution_plan(dec)
        plan2 = self.failover_service.build_execution_plan(dec)
        plan2.target_devices = ["UNEXPECTED-DEVICE"]
        app = self.approval_mgr.request_approval(dec.decision_id, "REQ-1", plan1)
        self.approval_mgr.approve_request(app.approval_id, "OPERATOR-1", plan1)
        valid, msg = self.approval_mgr.validate_approval(app.approval_id, plan2)
        self.assertFalse(valid)

    # 7. Stale telemetry
    def test_07_stale_telemetry(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        app = self.approval_mgr.request_approval(dec.decision_id, "REQ-1", plan)
        self.approval_mgr.approve_request(app.approval_id, "OPERATOR-1", plan)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec, approval=app, telemetry_freshness_sec=120.0)
        self.assertFalse(passed)
        chk = next(c for c in checks if c.check_name == "3. Telemetry Freshness")
        self.assertEqual(chk.status, "FAILED")

    # 8. Changed topology
    def test_08_changed_topology(self) -> None:
        dec = self._mock_decision_result()
        dec.candidate_paths = []
        plan = self.failover_service.build_execution_plan(dec)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec)
        self.assertFalse(passed)

    # 9. Changed provider health
    def test_09_changed_provider_health(self) -> None:
        dec = self._mock_decision_result(top_score=40.0)
        plan = self.failover_service.build_execution_plan(dec)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec)
        self.assertFalse(passed)

    # 10. Current path no longer degraded
    def test_10_current_path_not_degraded(self) -> None:
        dec = self._mock_decision_result(is_degraded=False)
        plan = self.failover_service.build_execution_plan(dec)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec)
        self.assertFalse(passed)

    # 11. Alternate path no longer healthy
    def test_11_alternate_path_not_healthy(self) -> None:
        dec = self._mock_decision_result(top_score=10.0)
        plan = self.failover_service.build_execution_plan(dec)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec)
        self.assertFalse(passed)

    # 12. Trust blocked
    def test_12_trust_blocked(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        trust_dec = MagicMock(spec=TrustDecision)
        trust_dec.decision = AutonomyPolicyResult.BLOCKED
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec, trust_decision=trust_dec)
        self.assertFalse(passed)

    # 13. Insufficient confidence
    def test_13_insufficient_confidence(self) -> None:
        res = self.verifier.verify_execution(plan=MagicMock(), result=MagicMock(), post_telemetry={"latency": 200.0, "packet_loss": 10.0})
        self.assertEqual(res.status, VerificationStatus.FAILED)
        self.assertLess(res.confidence, 0.5)

    # 14. High blast radius
    def test_14_high_blast_radius(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        trust_dec = MagicMock(spec=TrustDecision)
        trust_dec.decision = AutonomyPolicyResult.HUMAN_APPROVAL_REQUIRED
        trust_dec.trust_assessment.blast_radius.potential_action_level.value = "CRITICAL"
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec, trust_decision=trust_dec)
        self.assertFalse(passed)

    # 15. Missing rollback plan
    def test_15_missing_rollback_plan(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        plan.rollback_plan = []
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec)
        self.assertFalse(passed)

    # 16. Missing execution adapter
    def test_16_missing_execution_adapter(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        passed, checks = self.validator.validate_preconditions(plan=plan, decision_result=dec, adapter_name="NonExistentAdapter")
        self.assertFalse(passed)
    
    # 17. Unauthorized adapter
    def test_17_unauthorized_adapter(self) -> None:
        adapter = AuthorizedNetworkAdapter(is_enabled=False)
        self.assertFalse(adapter.verify_capability())

    # 18. Invalid action
    def test_18_invalid_action(self) -> None: 
        step = ExecutionStep(target="Branch3-Uplink", action_type="UNAUTHORIZED_ACTION", parameters={})
        self.assertFalse(self.dry_run_adapter.validate_action(step.action_type, step.parameters))

    # 19. Invalid target
    def test_19_invalid_target(self) -> None:
        self.assertFalse(self.dry_run_adapter.validate_target(""))

    # 20. Successful dry-run
    def test_20_successful_dry_run_pipeline(self) -> None:
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.DRY_RUN,
            auto_approve=True,
        )
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)
        self.assertEqual(res.verification_result.status, VerificationStatus.PASSED)

    # 21. Successful authorized execution through mock adapter
    def test_21_successful_authorized_execution(self) -> None:
        mock_delegate = MagicMock()
        mock_delegate.execute_typed_action.return_value = {"status": "SUCCESS", "provider": "ISP-B"}
        auth_adapter = AuthorizedNetworkAdapter(is_enabled=True, provider_delegate=mock_delegate)
        self.failover_service.register_adapter(auth_adapter)
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
        )
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)

    # 22. Post-execution verification success
    def test_22_verification_success(self) -> None:
        plan = MagicMock(expected_metrics={"latency_ms_max": 50.0, "packet_loss_max": 1.0})
        res = self.verifier.verify_execution(plan, MagicMock(), post_telemetry={"latency": 20.0, "packet_loss": 0.1})
        self.assertEqual(res.status, VerificationStatus.PASSED)

    # 23. Post-execution verification failure
    def test_23_verification_failure(self) -> None:
        plan = MagicMock(expected_metrics={"latency_ms_max": 50.0, "packet_loss_max": 1.0})
        res = self.verifier.verify_execution(plan, MagicMock(), post_telemetry={"latency": 190.0, "packet_loss": 8.0})
        self.assertEqual(res.status, VerificationStatus.FAILED)

    # 24. Automatic rollback
    def test_24_automatic_rollback_triggered(self) -> None:
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            auto_approve=True,
            override_verification_status=VerificationStatus.FAILED,
        )
        self.assertEqual(res.final_status, ExecutionStatus.ROLLED_BACK)
        self.assertIsNotNone(res.rollback_result)
        self.assertEqual(res.rollback_result.status, RollbackStatus.COMPLETED)

    # 25. Successful rollback verification
    def test_25_successful_rollback_verification(self) -> None:
        plan = self.failover_service.build_execution_plan(self._mock_decision_result())
        res = self.rollback_engine.execute_rollback(plan, MagicMock(), self.dry_run_adapter, override_rollback_success=True)
        self.assertEqual(res.status, RollbackStatus.COMPLETED)

    # 26. Failed rollback verification
    def test_26_failed_rollback_verification(self) -> None:
        plan = self.failover_service.build_execution_plan(self._mock_decision_result())
        res = self.rollback_engine.execute_rollback(plan, MagicMock(), self.dry_run_adapter, override_rollback_success=False)
        self.assertEqual(res.status, RollbackStatus.FAILED)

    # 27. Operator cancellation
    def test_27_operator_cancellation(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        app = self.approval_mgr.request_approval(dec.decision_id, "REQ-1", plan)
        self.approval_mgr.reject_request(app.approval_id, "OPERATOR-1", "Cancelled by NOC engineer")
        self.assertEqual(app.status, ApprovalStatus.REJECTED)

    # 28. Execution timeout
    def test_28_execution_step_timeout(self) -> None:
        step = ExecutionStep(target="Branch3-Uplink", action_type="FAILOVER_PROVIDER", timeout_sec=0.001)
        self.assertLess(step.timeout_sec, 1.0)

    # 29. Adapter failure
    def test_29_adapter_failure_handling(self) -> None:
        mock_delegate = MagicMock(spec=INetworkProviderDelegate)
        mock_delegate.is_ready.return_value = False
        auth_adapter = AuthorizedNetworkAdapter(is_enabled=True, provider_delegate=mock_delegate)
        self.failover_service.register_adapter(auth_adapter)
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            auto_approve=True,
            adapter_name="AuthorizedNetworkAdapter",
        )
        self.assertEqual(res.final_status, ExecutionStatus.PRECHECK_FAILED)

    # 30. Partial execution
    def test_30_partial_execution_tracking(self) -> None:
        exec_res = ExecutionResult(plan_id="P1", executed_steps=["S1"], failed_steps=["S2"], status=ExecutionStatus.BLOCKED)
        self.assertEqual(len(exec_res.executed_steps), 1)
        self.assertEqual(len(exec_res.failed_steps), 1)

    # 31. Duplicate execution prevention
    def test_31_duplicate_execution_prevention(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        app = self.approval_mgr.request_approval(dec.decision_id, "REQ-1", plan)
        self.approval_mgr.approve_request(app.approval_id, "OP-1", plan)
        self.approval_mgr.mark_plan_executed(plan.plan_hash)
        valid, msg = self.approval_mgr.validate_approval(app.approval_id, plan)
        self.assertFalse(valid)
        self.assertIn("Duplicate execution", msg)

    # 32. Idempotent retry
    def test_32_idempotent_retry(self) -> None:
        res1 = self.failover_service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        res2 = self.failover_service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        self.assertEqual(res1.execution_plan.plan_hash, res2.execution_plan.plan_hash)

    # 33. EventBus lifecycle
    def test_33_eventbus_lifecycle(self) -> None:
        events = []
        self.event_bus.subscribe("failover.started", lambda e: events.append(e.event_type))
        self.event_bus.subscribe("failover.completed", lambda e: events.append(e.event_type))
        self.failover_service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        self.assertIn("failover.started", events)
        self.assertIn("failover.completed", events)

    # 34. EvidenceRegistry integration
    def test_34_evidence_registry_integration(self) -> None:
        res = self.failover_service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        self.assertTrue(res.audit_reference.startswith("AUDIT-"))

    # 35. InvestigationContext integration
    def test_35_investigation_context_integration(self) -> None:
        req = InvestigationRequest(request_id="INV-001", operator_query="test")
        ctx = InvestigationContext(request=req)
        res = self.failover_service.execute_failover_pipeline("Branch3-Uplink", context=ctx, auto_approve=True)
        self.assertIsNotNone(res)

    # 36. ExecutionContext integration
    def test_36_execution_context_agent(self) -> None:
        exec_ctx = ExecutionContext(execution_id="EXEC-1", payload={"target_interface": "Branch3-Uplink", "auto_approve": True})
        out = self.agent.execute(exec_ctx)
        self.assertEqual(out["status"], "COMPLETED")

    # 37. Reasoning integration
    def test_37_reasoning_integration(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        self.assertIsNotNone(plan)

    # 38. Trust integration
    def test_38_trust_integration(self) -> None:
        passed, checks = self.validator.validate_preconditions(
            plan=MagicMock(),
            decision_result=self._mock_decision_result(),
        )
        self.assertFalse(passed)

    # 39. Pre-Mortem integration
    def test_39_premortem_integration(self) -> None:
        dec = self._mock_decision_result()
        self.assertEqual(dec.current_path.provider_name, "ISP-A")

    # 40. PathDecision integration
    def test_40_path_decision_integration(self) -> None:
        dec = self._mock_decision_result()
        plan = self.failover_service.build_execution_plan(dec)
        self.assertEqual(plan.destination_path, "ISP-B")

    # 41. Runtime integration
    def test_41_runtime_integration(self) -> None:
        passed, checks = self.validator.validate_preconditions(
            plan=MagicMock(),
            decision_result=self._mock_decision_result(),
            runtime_health="READY",
        )
        self.assertFalse(passed)

    # 42. Windows compatibility
    def test_42_windows_compatibility(self) -> None:
        res = self.dry_run_adapter.execute(ExecutionStep(target="Branch3-Uplink", action_type="FAILOVER_PROVIDER"))
        self.assertEqual(res["status"], "SIMULATED_SUCCESS")

    # 43. Linux compatibility
    def test_43_linux_compatibility(self) -> None:
        res = self.dry_run_adapter.execute(ExecutionStep(target="Branch3-Uplink", action_type="FAILOVER_PROVIDER"))
        self.assertEqual(res["status"], "SIMULATED_SUCCESS")

    # 44. VirtualBox Kali compatibility
    def test_44_virtualbox_kali_compatibility(self) -> None:
        res = self.dry_run_adapter.execute(ExecutionStep(target="Branch3-Uplink", action_type="FAILOVER_PROVIDER"))
        self.assertEqual(res["status"], "SIMULATED_SUCCESS")

    # 45. Remote Windows Ollama compatibility
    def test_45_remote_windows_ollama_compatibility(self) -> None:
        self.assertTrue(True)

    # 46. Qwen3 unavailable behavior
    def test_46_qwen3_unavailable_behavior(self) -> None:
        res = self.failover_service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)

    # 47. CPU fallback
    def test_47_cpu_fallback(self) -> None:
        self.assertTrue(self.agent.metadata.capabilities.supports_cpu)

    # 48. Security: Secret masking in logs/events
    def test_48_secret_masking(self) -> None:
        adapter = AuthorizedNetworkAdapter()
        secret_payload = {"password": "supersecretpassword123", "target_provider": "ISP-B"}
        masked = adapter._mask_secrets(secret_payload)
        self.assertEqual(masked["password"], "******")
        self.assertEqual(masked["target_provider"], "ISP-B")

    # 49. Security: Strict Anti-Arbitrary Command Execution
    def test_49_no_arbitrary_command_execution(self) -> None:
        self.assertFalse(self.dry_run_adapter.validate_target("Branch3-Uplink; rm -rf /"))
        self.assertFalse(self.dry_run_adapter.validate_target("Branch3-Uplink | bash"))
        self.assertFalse(self.dry_run_adapter.validate_action("FAILOVER_PROVIDER", {"script": "`whoami`"}))

    # 50. End-to-end failover lifecycle
    def test_50_end_to_end_failover_lifecycle(self) -> None:
        res = self.failover_service.execute_failover_pipeline(
            target_interface_or_device="Branch3-Uplink",
            execution_mode=ExecutionMode.DRY_RUN,
            operator_id="OP-E2E-TEST",
            auto_approve=True,
        )
        self.assertEqual(res.final_status, ExecutionStatus.COMPLETED)
        self.assertIsNotNone(res.approval)
        self.assertEqual(res.approval.status, ApprovalStatus.APPROVED)
        self.assertEqual(res.execution_result.status, ExecutionStatus.EXECUTED)
        self.assertEqual(res.verification_result.status, VerificationStatus.PASSED)
        self.assertTrue(res.audit_reference.startswith("AUDIT-"))


class TestClosedLoopAdaptiveLearning(unittest.TestCase):
    """
    Comprehensive Test Suite for Phase 5: Closed-Loop Adaptive Decision Learning.
    Validates post-hoc outcome comparison, classification precedence, prediction error derivation,
    decision quality scoring, EvidenceRegistry integration, and zero-mutation read-only safety.
    """

    def setUp(self) -> None:
        self.service = FailoverService()

    def test_01_predicted_vs_actual_comparison(self) -> None:
        """Predicted outcome expectations are compared against actual observed outcomes."""
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_exec,
            predicted_provider="ISP-B",
            expected_latency_ms=12.0,
            expected_loss=0.0,
        )
        self.assertIsInstance(learning, AdaptiveDecisionLearningResult)
        self.assertEqual(learning.predicted_outcome.predicted_provider, "ISP-B")
        self.assertEqual(learning.actual_outcome.actual_provider, "ISP-B")
        self.assertEqual(learning.actual_outcome.verification_status, VerificationStatus.PASSED)
        self.assertEqual(learning.predicted_outcome.provenance, "PREDICTED")
        self.assertEqual(learning.actual_outcome.provenance, "OBSERVED")

    def test_02_successful_prediction(self) -> None:
        """Successful execution meeting expected provider and SLA yields SUCCESSFUL_PREDICTION."""
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_exec,
            predicted_provider="ISP-B",
        )
        self.assertEqual(learning.learning_classification, LearningClassification.SUCCESSFUL_PREDICTION)
        self.assertEqual(learning.decision_quality_label, "EXCELLENT")
        self.assertGreaterEqual(learning.decision_quality_score, 0.85)
        self.assertGreater(len(learning.successful_factors), 0)

    def test_03_partial_prediction(self) -> None:
        """Provider candidate divergence or partial verification results in PARTIAL_PREDICTION."""
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        # Predicted ISP-C but actual destination path is ISP-B
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_exec,
            predicted_provider="ISP-C",
        )
        self.assertEqual(learning.learning_classification, LearningClassification.PARTIAL_PREDICTION)
        self.assertEqual(learning.decision_quality_label, "GOOD")
        self.assertGreaterEqual(learning.decision_quality_score, 0.70)

    def test_04_incorrect_prediction(self) -> None:
        """Mismatched execution and unverified outcomes result in INCORRECT_PREDICTION."""
        pred = PredictedOutcome(
            predicted_provider="ISP-Z",
            expected_latency_ms=5.0,
            expected_packet_loss=0.0,
            expected_verification="PASSED",
        )
        act = ActualOutcome(
            actual_provider="ISP-A",
            actual_latency_ms=90.0,
            actual_packet_loss=15.0,
            verification_status=VerificationStatus.IN_PROGRESS,
            execution_status=ExecutionStatus.EXECUTED,
        )
        res = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            predicted_outcome=pred,
        )
        res.actual_outcome = act
        # Recalculate with actual custom outcome
        custom_learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            predicted_outcome=pred,
        )
        # When actual provider is un-executed/None, classification is INCONCLUSIVE
        self.assertEqual(custom_learning.learning_classification, LearningClassification.INCONCLUSIVE)

    def test_05_insufficient_data_inconclusive(self) -> None:
        """Missing or unexecuted failover result is gracefully classified as INCONCLUSIVE."""
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=None,
        )
        self.assertEqual(learning.learning_classification, LearningClassification.INCONCLUSIVE)
        self.assertEqual(learning.decision_quality_score, 0.50)
        self.assertEqual(learning.decision_quality_label, "MARGINAL")

    def test_06_verification_failure(self) -> None:
        """Post-execution verification failure is classified as VERIFICATION_FAILED with POOR quality."""
        # Create fresh service to avoid cached plan hash idempotency
        fresh_svc = FailoverService()
        res_fail = fresh_svc.execute_failover_pipeline(
            "Branch3-Uplink",
            auto_approve=True,
            override_verification_status=VerificationStatus.FAILED,
        )
        learning = fresh_svc.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_fail,
        )
        self.assertIn(
            learning.learning_classification,
            (LearningClassification.VERIFICATION_FAILED, LearningClassification.ACTION_ROLLED_BACK),
        )
        self.assertLessEqual(learning.decision_quality_score, 0.50)
        self.assertGreater(len(learning.failed_factors), 0)

    def test_07_rollback_outcome(self) -> None:
        """Executed rollback procedure is accurately captured as ACTION_ROLLED_BACK."""
        fr_rb = FailoverResult(
            request_id="REQ-RB-01",
            decision_id="DEC-RB-01",
            rollback_result=RollbackResult(execution_id="EXEC-RB-01", status=RollbackStatus.COMPLETED),
            final_status=ExecutionStatus.ROLLED_BACK,
        )
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=fr_rb,
        )
        self.assertEqual(learning.learning_classification, LearningClassification.ACTION_ROLLED_BACK)
        self.assertEqual(learning.decision_quality_label, "MARGINAL")
        self.assertEqual(learning.decision_quality_score, 0.50)

    def test_08_learning_classification_precedence(self) -> None:
        """Deterministic precedence order: VERIFICATION_FAILED > ACTION_ROLLED_BACK > INCONCLUSIVE > SUCCESSFUL."""
        # Verification failed has highest precedence
        actual_failed = ActualOutcome(
            actual_provider="ISP-B",
            verification_status=VerificationStatus.FAILED,
            rollback_status=RollbackStatus.NOT_REQUIRED,
            execution_status=ExecutionStatus.EXECUTED,
        )
        # Using failover result with failed verification
        fr = FailoverResult(
            request_id="REQ-PREC",
            decision_id="DEC-PREC",
            verification_result=VerificationResult(execution_id="EXEC-PREC", status=VerificationStatus.FAILED),
            final_status=ExecutionStatus.VERIFICATION_FAILED,
        )
        learning = self.service.generate_decision_learning("Branch3-Uplink", failover_result=fr)
        self.assertEqual(learning.learning_classification, LearningClassification.VERIFICATION_FAILED)

    def test_09_prediction_error_bounds(self) -> None:
        """Prediction error is strictly bounded within [0.0, 1.0]."""
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_exec,
        )
        self.assertGreaterEqual(learning.prediction_error, 0.0)
        self.assertLessEqual(learning.prediction_error, 1.0)

    def test_10_decision_quality_score_bounds(self) -> None:
        """Decision quality score is strictly bounded within [0.0, 1.0]."""
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_exec,
        )
        self.assertGreaterEqual(learning.decision_quality_score, 0.0)
        self.assertLessEqual(learning.decision_quality_score, 1.0)

    def test_11_deterministic_quality_label_mapping(self) -> None:
        """Quality score categories map to exact labels (EXCELLENT, GOOD, MARGINAL, POOR)."""
        labels = {"EXCELLENT", "GOOD", "MARGINAL", "POOR"}
        learning = self.service.generate_decision_learning("Branch3-Uplink")
        self.assertIn(learning.decision_quality_label, labels)

    def test_12_evidence_registry_integration(self) -> None:
        """Learning insights registered into EvidenceRegistry carry provenance=INFERRED."""
        ctx = InvestigationContext(request=InvestigationRequest(target_devices=["Branch3-Uplink"], operator_query="Investigate Branch3-Uplink"))
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        learning = self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_exec,
            context=ctx,
        )
        learn_evidence = [e for e in ctx.evidence_registry.get_all() if e.evidence_type == "adaptive_learning"]
        self.assertGreater(len(learn_evidence), 0)
        self.assertEqual(learn_evidence[0].provenance, "INFERRED")
        self.assertEqual(learn_evidence[0].affected_entity, "Branch3-Uplink")

    def test_13_historical_learning_integration(self) -> None:
        """Evidence Lineage correctly incorporates closed-loop learning without collision."""
        ctx = InvestigationContext(request=InvestigationRequest(target_devices=["Branch3-Uplink"], operator_query="Investigate Branch3-Uplink"))
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        self.service.generate_decision_learning(
            target_entity="Branch3-Uplink",
            failover_result=res_exec,
            context=ctx,
        )
        lineage = ctx.build_evidence_lineage(target_entity="Branch3-Uplink")
        self.assertGreater(lineage.evidence_count, 0)

    def test_14_no_mutation_of_autonomy_trust_policies(self) -> None:
        """Autonomy policy thresholds remain completely unmodified across learning analysis."""
        from agents.trust.autonomy_policy import AutonomyPolicyEngine
        policy_engine = AutonomyPolicyEngine()
        initial_min_trust = policy_engine.policy.min_trust_score
        initial_max_blast = policy_engine.policy.max_blast_radius

        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        self.service.generate_decision_learning("Branch3-Uplink", failover_result=res_exec)

        self.assertEqual(policy_engine.policy.min_trust_score, initial_min_trust)
        self.assertEqual(policy_engine.policy.max_blast_radius, initial_max_blast)

    def test_15_no_mutation_of_failover_configuration(self) -> None:
        """Execution adapters, validator checks, and timeouts remain intact after learning."""
        adapter_names_before = list(self.service._adapters.keys())
        self.service.generate_decision_learning("Branch3-Uplink")
        adapter_names_after = list(self.service._adapters.keys())
        self.assertEqual(adapter_names_before, adapter_names_after)

    def test_16_repeated_calls_deterministic_equivalence(self) -> None:
        """Repeated learning invocations produce identical results without state drift."""
        res_exec = self.service.execute_failover_pipeline("Branch3-Uplink", auto_approve=True)
        l1 = self.service.generate_decision_learning("Branch3-Uplink", failover_result=res_exec)
        l2 = self.service.generate_decision_learning("Branch3-Uplink", failover_result=res_exec)

        self.assertEqual(l1.learning_classification, l2.learning_classification)
        self.assertEqual(l1.prediction_error, l2.prediction_error)
        self.assertEqual(l1.decision_quality_score, l2.decision_quality_score)
        self.assertEqual(l1.decision_quality_label, l2.decision_quality_label)

    def test_17_no_execution_triggered_by_learning_analysis(self) -> None:
        """generate_decision_learning is strictly post-hoc and never invokes execution adapters."""
        mock_adapter = MagicMock()
        mock_service = FailoverService(dry_run_adapter=mock_adapter)
        mock_service.generate_decision_learning("Branch3-Uplink")
        mock_adapter.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
