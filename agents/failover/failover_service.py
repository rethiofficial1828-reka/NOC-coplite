"""
Failover Service Module for Enterprise Controlled Failover Execution Engine.

Domain service orchestrating approval management, 16-point pre-execution validation,
typed adapter execution (DryRun / Authorized), closed-loop post-execution verification,
automated rollback execution, idempotency checking, and append-only audit logging.
"""

from datetime import datetime, timezone
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.failover.approval_manager import ApprovalManager
from agents.failover.authorized_execution_adapter import AuthorizedNetworkAdapter
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.execution_adapter import IExecutionAdapter
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
    ProductionExecutionDisabledError,
    RollbackResult,
    RollbackStatus,
    VerificationResult,
    VerificationStatus,
)
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.path_decision.path_models import PathDecisionResult
from agents.z3_verifier.z3_models import Z3VerificationRequest, Z3VerificationStatus
from agents.z3_verifier.z3_verifier import Z3FormalVerifier

logger = get_agent_logger("FailoverService")


class FailoverService:
    """
    Orchestration service for closed-loop network failover execution.
    """

    def __init__(
        self,
        approval_manager: Optional[ApprovalManager] = None,
        validator: Optional[PreExecutionValidator] = None,
        verifier: Optional[PostExecutionVerifier] = None,
        rollback_engine: Optional[RollbackEngine] = None,
        dry_run_adapter: Optional[DryRunExecutionAdapter] = None,
        authorized_adapter: Optional[AuthorizedNetworkAdapter] = None,
        path_decision_service: Optional[Any] = None,
        z3_verifier: Optional[Z3FormalVerifier] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._approval_manager = approval_manager or ApprovalManager()
        self._validator = validator or PreExecutionValidator(approval_manager=self._approval_manager)
        self._verifier = verifier or PostExecutionVerifier()
        self._rollback_engine = rollback_engine or RollbackEngine()
        self._dry_run_adapter = dry_run_adapter or DryRunExecutionAdapter()
        self._authorized_adapter = authorized_adapter or AuthorizedNetworkAdapter()
        self._z3_verifier = z3_verifier or Z3FormalVerifier()
        if path_decision_service is None:
            from agents.path_decision.decision_service import PathDecisionService
            self._path_decision_service = PathDecisionService()
        else:
            self._path_decision_service = path_decision_service
        self._event_bus = event_bus

        self._adapters: Dict[str, IExecutionAdapter] = {
            self._dry_run_adapter.adapter_name: self._dry_run_adapter,
            self._authorized_adapter.adapter_name: self._authorized_adapter,
        }

        self._executed_results: Dict[str, FailoverResult] = {}
        self._lock = threading.RLock()

    @property
    def approval_manager(self) -> ApprovalManager:
        """Public accessor for the approval manager (required by tests)."""
        return self._approval_manager

    @property
    def pre_validator(self) -> PreExecutionValidator:
        """Public accessor for the pre-execution validator (required by tests)."""
        return self._validator

    @property
    def rollback_engine(self) -> RollbackEngine:
        """Public accessor for the rollback engine (required by tests)."""
        return self._rollback_engine

    def register_adapter(self, adapter: IExecutionAdapter) -> None:
        """Register custom pre-authorized execution adapter."""
        with self._lock:
            self._adapters[adapter.adapter_name] = adapter
            logger.info(f"Registered execution adapter: '{adapter.adapter_name}'")

    def build_execution_plan(self, decision_result: PathDecisionResult) -> ExecutionPlan:
        """
        Build structured ExecutionPlan from PathDecisionResult.
        """
        rec = decision_result.recommendation
        current_p = decision_result.current_path.provider_name if decision_result.current_path else "ISP-A"
        rec_p = rec.recommended_provider or current_p
        target_dev = decision_result.current_path.source_device if decision_result.current_path else "Branch3-Uplink"

        step1 = ExecutionStep(
            sequence=1,
            adapter="DryRunExecutionAdapter",
            target=target_dev,
            action_type="FAILOVER_PROVIDER",
            parameters={
                "source_provider": current_p,
                "target_provider": rec_p,
                "interface": decision_result.current_path.wan_interface if decision_result.current_path else "Branch3-Uplink",
            },
            reversible=True,
        )

        rollback_step = ExecutionStep(
            sequence=2,
            adapter="DryRunExecutionAdapter",
            target=target_dev,
            action_type="FAILBACK_PROVIDER",
            parameters={
                "source_provider": rec_p,
                "target_provider": current_p,
                "interface": decision_result.current_path.wan_interface if decision_result.current_path else "Branch3-Uplink",
            },
            reversible=True,
        )

        plan = ExecutionPlan(
            decision_id=decision_result.decision_id,
            source_path=current_p,
            destination_path=rec_p,
            target_devices=[target_dev],
            steps=[step1],
            expected_changes={"primary_provider": rec_p},
            expected_metrics={
                "latency_ms_max": 35.0,
                "packet_loss_max": 0.5,
                "utilization_max": 65.0,
                "failure_risk_max": 0.15,
            },
            rollback_plan=[rollback_step],
            risk=ExecutionRisk.LOW,
            blast_radius="LOW",
            plan_hash="",
        )
        plan.plan_hash = self._approval_manager.compute_plan_hash(plan)
        return plan

    def execute_failover_pipeline(
        self,
        target_interface_or_device: str,
        execution_mode: ExecutionMode = ExecutionMode.DRY_RUN,
        operator_id: str = "SYSTEM_OPERATOR",
        auto_approve: bool = False,
        adapter_name: str = "DryRunExecutionAdapter",
        context: Optional[InvestigationContext] = None,
        override_verification_status: Optional[VerificationStatus] = None,
        override_rollback_success: bool = True,
        override_telemetry: Optional[Dict[str, float]] = None,
        override_risk: Optional[float] = None,
    ) -> FailoverResult:
        """
        Execute full closed-loop failover lifecycle.
        """
        with self._lock:
            if execution_mode == ExecutionMode.PRODUCTION_AUTHORIZED:
                logger.error("PRODUCTION_AUTHORIZED execution requested but permanently disabled in v1.2.")
                raise ProductionExecutionDisabledError(
                    "PRODUCTION_AUTHORIZED is permanently disabled in NOC-Copilot v1.2. "
                    "Production network mutation is not permitted."
                )

            req_id = str(uuid.uuid4())
            self._publish_event("failover.started", {"request_id": req_id, "target": target_interface_or_device, "mode": execution_mode.value})

            # 1. Path Decision & Multi-Agent Evaluation
            decision_res = self._path_decision_service.evaluate_path_decision(
                target_interface_or_device=target_interface_or_device,
                request_id=req_id,
                context=context,
                override_telemetry=override_telemetry,
                override_risk=override_risk,
            )

            # 2. Build Execution Plan
            plan = self.build_execution_plan(decision_res)

            # Idempotency check: if plan_hash already executed successfully, return previous result
            if plan.plan_hash in self._approval_manager._executed_plan_hashes:
                prev = next((r for r in self._executed_results.values() if r.execution_plan and r.execution_plan.plan_hash == plan.plan_hash), None)
                if prev:
                    logger.info(f"FailoverService: Returning idempotent result for plan hash '{plan.plan_hash[:8]}...'")
                    return prev

            # 3. Request Approval
            approval = self._approval_manager.request_approval(
                decision_id=decision_res.decision_id,
                request_id=req_id,
                plan=plan,
                operator_id=operator_id,
            )
            self._publish_event("failover.approval.required", {"request_id": req_id, "approval_id": approval.approval_id, "plan_hash": plan.plan_hash})

            if auto_approve:
                self._approval_manager.approve_request(approval.approval_id, operator_id, plan, notes="Auto-approved for execution test")

            # 4. Resolve Adapter & Pre-Execution Validation (16 Prechecks)
            adapter = self._adapters.get(adapter_name, self._dry_run_adapter)
            self._publish_event("failover.precheck.started", {"request_id": req_id})
            prechecks_ok, precheck_list = self._validator.validate_preconditions(
                plan=plan,
                decision_result=decision_res,
                approval=approval,
                adapter_name=adapter_name,
                adapter_obj=adapter,
            )
            self._publish_event("failover.precheck.completed", {"request_id": req_id, "passed": prechecks_ok})

            if not prechecks_ok:
                rec_res = FailoverResult(
                    failover_id=str(uuid.uuid4()),
                    request_id=req_id,
                    decision_id=decision_res.decision_id,
                    approval=approval,
                    prechecks=precheck_list,
                    execution_plan=plan,
                    final_status=ExecutionStatus.PRECHECK_FAILED,
                    audit_reference=self._write_audit_log(req_id, "PRECHECK_FAILED"),
                )
                self._publish_event("failover.failed", {"request_id": req_id, "status": "PRECHECK_FAILED"})
                return rec_res

            # 4b. Formal Z3 Safety Verification Gate
            from config.settings import WAN_PROVIDER_REGISTRY
            source_prov = plan.source_path
            target_prov = plan.destination_path
            target_dev = plan.target_devices[0] if plan.target_devices else "branch3-uplink"
            wan_if = plan.steps[0].parameters.get("interface", "Branch3-Uplink") if plan.steps else "Branch3-Uplink"
            p_def = next((p for p in WAN_PROVIDER_REGISTRY if p["provider_id"] == target_prov), None)
            is_sim = (p_def.get("is_simulated", False) if p_def else False) or (target_prov in ("ISP-C", "ISP-D"))

            z3_req = Z3VerificationRequest(
                plan_id=plan.plan_id,
                source_provider=source_prov,
                target_provider=target_prov,
                target_device=target_dev,
                wan_interface=wan_if,
                next_hop=p_def.get("next_hop") if p_def else None,
                is_simulated=is_sim,
                execution_mode=execution_mode.value,
                predicted_blast_radius_pct=float(decision_res.gnn_blast_radius.get("predicted_blast_radius_pct", 10.0)) if decision_res.gnn_blast_radius else 10.0,
            )
            z3_verdict = self._z3_verifier.verify_plan(z3_req)
            self._publish_event("failover.z3_verification.completed", {"request_id": req_id, "status": z3_verdict.status.value, "is_safe": z3_verdict.is_safe})

            if not z3_verdict.is_safe:
                logger.error(f"Z3 Formal Verification UNSAT: {z3_verdict.proof_summary} - halting execution.")
                rec_res = FailoverResult(
                    failover_id=str(uuid.uuid4()),
                    request_id=req_id,
                    decision_id=decision_res.decision_id,
                    approval=approval,
                    prechecks=precheck_list,
                    execution_plan=plan,
                    z3_verification=z3_verdict.model_dump(mode="json"),
                    digital_twin_simulation=decision_res.digital_twin_simulation,
                    gnn_blast_radius=decision_res.gnn_blast_radius,
                    final_status=ExecutionStatus.BLOCKED,
                    audit_reference=self._write_audit_log(req_id, "Z3_VERIFICATION_FAILED"),
                )
                self._publish_event("failover.failed", {"request_id": req_id, "status": "Z3_VERIFICATION_FAILED"})
                return rec_res

            # 5. Resolve Adapter
            adapter = self._adapters.get(adapter_name, self._dry_run_adapter)

            # 6. Execute Execution Plan
            self._publish_event("failover.execution.started", {"request_id": req_id, "adapter": adapter.adapter_name})
            exec_id = str(uuid.uuid4())
            executed_steps: List[str] = []
            failed_steps: List[str] = []
            adapter_results: Dict[str, Any] = {}

            start_t = datetime.now(timezone.utc)
            exec_success = True

            for step in plan.steps:
                try:
                    res = adapter.execute(step)
                    executed_steps.append(step.step_id)
                    adapter_results[step.step_id] = res
                except Exception as e:
                    exec_success = False
                    failed_steps.append(step.step_id)
                    adapter_results[step.step_id] = {"error": str(e)}
                    break

            exec_status = ExecutionStatus.EXECUTED if exec_success else ExecutionStatus.BLOCKED
            exec_res = ExecutionResult(
                execution_id=exec_id,
                plan_id=plan.plan_id,
                status=exec_status,
                mode=execution_mode,
                started_at=start_t,
                completed_at=datetime.now(timezone.utc),
                executed_steps=executed_steps,
                failed_steps=failed_steps,
                adapter_results=adapter_results,
            )
            self._publish_event("failover.execution.completed", {"request_id": req_id, "status": exec_status.value})

            # Record plan hash executed in approval manager
            if exec_success:
                self._approval_manager.mark_plan_executed(plan.plan_hash)

            # 7. Post-Execution Closed-Loop Verification
            self._publish_event("failover.verification.started", {"request_id": req_id})
            verif_res = self._verifier.verify_execution(
                plan=plan,
                result=exec_res,
                override_status=override_verification_status,
            )
            self._publish_event("failover.verification.completed", {"request_id": req_id, "status": verif_res.status.value})

            # 8. Check Closed-Loop Outcome: Verification Passed or Rollback Required
            rollback_res: Optional[RollbackResult] = None
            if not exec_success:
                # Adapter step execution failed -> Trigger Automatic Rollback
                self._publish_event("failover.rollback.started", {"request_id": req_id})
                rollback_res = self._rollback_engine.execute_rollback(
                    plan=plan,
                    execution_result=exec_res,
                    adapter=adapter,
                    rollback_reason="Execution step failed",
                    override_rollback_success=override_rollback_success,
                )
                self._publish_event("failover.rollback.completed", {"request_id": req_id, "status": rollback_res.status.value})

                if rollback_res.status == RollbackStatus.COMPLETED:
                    final_status = ExecutionStatus.ROLLED_BACK
                else:
                    final_status = ExecutionStatus.ROLLBACK_FAILED
            elif verif_res.status == VerificationStatus.PASSED:
                final_status = ExecutionStatus.COMPLETED
                self._publish_event("failover.completed", {"request_id": req_id, "decision": "SUCCESS"})
            else:
                # Trigger Automatic Rollback due to verification failure
                self._publish_event("failover.rollback.started", {"request_id": req_id})
                rollback_res = self._rollback_engine.execute_rollback(
                    plan=plan,
                    execution_result=exec_res,
                    adapter=adapter,
                    rollback_reason=f"Verification status: {verif_res.status.value}",
                    override_rollback_success=override_rollback_success,
                )
                self._publish_event("failover.rollback.completed", {"request_id": req_id, "status": rollback_res.status.value})

                if rollback_res.status == RollbackStatus.COMPLETED:
                    final_status = ExecutionStatus.ROLLED_BACK
                else:
                    final_status = ExecutionStatus.ROLLBACK_FAILED

            audit_ref = self._write_audit_log(req_id, final_status.value)
            result = FailoverResult(
                failover_id=str(uuid.uuid4()),
                request_id=req_id,
                decision_id=decision_res.decision_id,
                approval=approval,
                prechecks=precheck_list,
                execution_plan=plan,
                execution_result=exec_res,
                verification_result=verif_res,
                rollback_result=rollback_res,
                z3_verification=z3_verdict.model_dump(mode="json") if 'z3_verdict' in locals() else None,
                digital_twin_simulation=decision_res.digital_twin_simulation,
                gnn_blast_radius=decision_res.gnn_blast_radius,
                final_status=final_status,
                audit_reference=audit_ref,
                created_at=datetime.now(timezone.utc),
            )

            self._executed_results[result.failover_id] = result

            logger.info(
                f"FailoverService completed lifecycle for request '{req_id}': "
                f"Final Status = '{final_status.value}', Audit Ref = '{audit_ref}'"
            )

            return result

    def _write_audit_log(self, request_id: str, status: str) -> str:
        """Write audit entry to air-gapped telemetry/audit log."""
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "telemetry.db")
        audit_id = f"AUDIT-{uuid.uuid4().hex[:8].upper()}"

        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                try:
                    with conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS failover_audit (
                                audit_id TEXT PRIMARY KEY,
                                request_id TEXT,
                                status TEXT,
                                timestamp TEXT
                            )
                        """
                        )
                        cursor.execute(
                            "INSERT INTO failover_audit (audit_id, request_id, status, timestamp) VALUES (?, ?, ?, ?)",
                            (audit_id, request_id, status, datetime.now(timezone.utc).isoformat()),
                        )
                finally:
                    conn.close()
            except Exception as e:
                logger.warning(f"Audit log write failed: {e}")

        return audit_id

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Publish event to EventBus."""
        if self._event_bus:
            try:
                evt = Event(
                    event_type=event_type,
                    source="FailoverService",
                    payload=payload,
                )
                self._event_bus.publish(evt)
            except Exception as e:
                logger.warning(f"EventBus publish error for '{event_type}': {e}")

    def generate_decision_learning(
        self,
        target_entity: str,
        failover_result: Optional[FailoverResult] = None,
        context: Optional[InvestigationContext] = None,
        predicted_outcome: Optional[PredictedOutcome] = None,
        predicted_provider: Optional[str] = None,
        predicted_risk: Optional[float] = None,
        expected_latency_ms: Optional[float] = None,
        expected_loss: Optional[float] = None,
        expected_impact: Optional[str] = None,
    ) -> AdaptiveDecisionLearningResult:
        """
        Execute post-hoc closed-loop adaptive decision learning analysis.

        CRITICAL ARCHITECTURAL CONSTRAINTS:
        - POST-HOC and READ/ANALYZE ONLY.
        - NEVER triggers failover, verification, or rollback.
        - NEVER mutates autonomy policy, trust parameters, or provider weights.
        - Deterministic quality score and classification.
        """
        with self._lock:
            import time
            start_time = time.perf_counter()
            inv_id = context.context_id if context and hasattr(context, "context_id") else str(uuid.uuid4())
            exec_id = failover_result.execution_result.execution_id if (failover_result and failover_result.execution_result) else None

            # 1. Synthesize / Ingest Predicted Outcome
            if predicted_outcome is None:
                p_provider = predicted_provider or "ISP-B"
                p_risk = predicted_risk if predicted_risk is not None else 0.88
                p_lat = expected_latency_ms if expected_latency_ms is not None else 12.0
                p_loss = expected_loss if expected_loss is not None else 0.0
                p_impact = expected_impact or "Latency restoration to <= 15ms with 0.0% loss"
                pred_out = PredictedOutcome(
                    predicted_risk=p_risk,
                    predicted_provider=p_provider,
                    expected_latency_ms=p_lat,
                    expected_packet_loss=p_loss,
                    expected_verification="PASSED",
                    expected_impact=p_impact,
                    provenance="PREDICTED",
                )
            else:
                pred_out = predicted_outcome

            # 2. Extract Actual Outcome from Completed Failover Result
            if failover_result is not None:
                ver_res = failover_result.verification_result
                rb_res = failover_result.rollback_result
                ex_res = failover_result.execution_result

                v_status = ver_res.status if ver_res else VerificationStatus.NOT_STARTED
                rb_status = rb_res.status if rb_res else RollbackStatus.NOT_REQUIRED
                ex_status = failover_result.final_status

                # Extract observed telemetry from verification checks if present
                obs_lat: Optional[float] = None
                obs_loss: Optional[float] = None
                if ver_res and ver_res.checks:
                    for chk in ver_res.checks:
                        metric_name = (chk.metric or "").lower()
                        if "latency" in metric_name:
                            obs_lat = chk.observed_value
                        elif "loss" in metric_name:
                            obs_loss = chk.observed_value

                # Fallback to defaults based on execution state
                if obs_lat is None:
                    obs_lat = 12.0 if v_status == VerificationStatus.PASSED else (45.0 if v_status == VerificationStatus.FAILED else None)
                if obs_loss is None:
                    obs_loss = 0.0 if v_status == VerificationStatus.PASSED else (5.0 if v_status == VerificationStatus.FAILED else None)

                act_provider = (
                    failover_result.execution_plan.destination_path
                    if (failover_result.execution_plan and failover_result.execution_plan.destination_path)
                    else pred_out.predicted_provider
                )

                act_out = ActualOutcome(
                    actual_provider=act_provider,
                    actual_latency_ms=obs_lat,
                    actual_packet_loss=obs_loss,
                    verification_status=v_status,
                    rollback_status=rb_status,
                    execution_status=ex_status,
                    restoration_status=rb_res.restoration_status.value if (rb_res and hasattr(rb_res, "restoration_status")) else None,
                    provenance="OBSERVED",
                )
            else:
                act_out = ActualOutcome(
                    actual_provider=None,
                    actual_latency_ms=None,
                    actual_packet_loss=None,
                    verification_status=VerificationStatus.NOT_STARTED,
                    rollback_status=RollbackStatus.NOT_REQUIRED,
                    execution_status=ExecutionStatus.NOT_STARTED,
                    provenance="OBSERVED",
                )

            # 3. Deterministic Precedence-Based Learning Classification
            # Precedence:
            # 1. VERIFICATION_FAILED
            # 2. ACTION_ROLLED_BACK
            # 3. INCONCLUSIVE when required comparison data is missing
            # 4. SUCCESSFUL_PREDICTION
            # 5. PARTIAL_PREDICTION
            # 6. INCORRECT_PREDICTION
            # 7. ACTION_SUCCESSFUL

            if act_out.verification_status == VerificationStatus.FAILED:
                classification = LearningClassification.VERIFICATION_FAILED
            elif act_out.rollback_status == RollbackStatus.COMPLETED or act_out.execution_status == ExecutionStatus.ROLLED_BACK:
                classification = LearningClassification.ACTION_ROLLED_BACK
            elif act_out.execution_status in (ExecutionStatus.NOT_STARTED, ExecutionStatus.CANCELLED) or act_out.actual_provider is None:
                classification = LearningClassification.INCONCLUSIVE
            elif act_out.verification_status == VerificationStatus.PASSED:
                if act_out.actual_provider == pred_out.predicted_provider:
                    classification = LearningClassification.SUCCESSFUL_PREDICTION
                else:
                    classification = LearningClassification.PARTIAL_PREDICTION
            elif act_out.verification_status == VerificationStatus.PARTIAL:
                classification = LearningClassification.PARTIAL_PREDICTION
            else:
                classification = LearningClassification.INCORRECT_PREDICTION

            # 4. Derive Prediction Error [0.0, 1.0]
            # Only compute error components where both predicted and actual values exist.
            error_components: List[float] = []
            if pred_out.predicted_provider and act_out.actual_provider:
                error_components.append(0.0 if pred_out.predicted_provider == act_out.actual_provider else 0.5)

            if pred_out.expected_latency_ms is not None and act_out.actual_latency_ms is not None:
                lat_err = min(0.5, abs(act_out.actual_latency_ms - pred_out.expected_latency_ms) / 100.0)
                error_components.append(lat_err)

            if pred_out.expected_packet_loss is not None and act_out.actual_packet_loss is not None:
                loss_err = min(0.5, abs(act_out.actual_packet_loss - pred_out.expected_packet_loss) / 20.0)
                error_components.append(loss_err)

            if act_out.verification_status != VerificationStatus.NOT_STARTED:
                v_expected_passed = (pred_out.expected_verification.upper() == "PASSED")
                v_actual_passed = (act_out.verification_status == VerificationStatus.PASSED)
                error_components.append(0.0 if v_expected_passed == v_actual_passed else 0.5)

            if error_components:
                prediction_error = round(min(1.0, max(0.0, sum(error_components) / len(error_components))), 2)
            else:
                prediction_error = 0.0

            # 5. Derive Decision Quality Score & Label [0.0, 1.0]
            # Derived from verification status, rollback result, and prediction accuracy
            if classification == LearningClassification.SUCCESSFUL_PREDICTION:
                quality_score = round(max(0.85, 1.0 - prediction_error * 0.5), 2)
                quality_label = "EXCELLENT"
            elif classification == LearningClassification.PARTIAL_PREDICTION:
                quality_score = round(max(0.70, 0.85 - prediction_error * 0.3), 2)
                quality_label = "GOOD"
            elif classification == LearningClassification.ACTION_ROLLED_BACK:
                quality_score = 0.50
                quality_label = "MARGINAL"
            elif classification == LearningClassification.INCONCLUSIVE:
                quality_score = 0.50
                quality_label = "MARGINAL"
            elif classification == LearningClassification.VERIFICATION_FAILED:
                quality_score = 0.20
                quality_label = "POOR"
            else:
                quality_score = 0.30
                quality_label = "POOR"

            # 6. Factor Analysis & Lessons Learned
            successful_factors: List[str] = []
            failed_factors: List[str] = []
            lessons_learned: List[str] = []
            recommendation_signals: List[str] = []

            if act_out.verification_status == VerificationStatus.PASSED:
                successful_factors.append(f"Provider candidate '{act_out.actual_provider}' successfully restored SLA compliance.")
                successful_factors.append("Multi-factor path decision accurately identified optimal egress route.")
                successful_factors.append("Pre-execution validation (16 checks) ensured clean configuration transition.")
                lessons_learned.append(f"Path failover to '{act_out.actual_provider}' is highly effective for interface congestion on {target_entity}.")
                recommendation_signals.append(f"Retain '{act_out.actual_provider}' as preferred failover target for similar degradation signatures.")
            elif act_out.verification_status == VerificationStatus.FAILED:
                failed_factors.append(f"Post-execution verification failed on candidate provider '{act_out.actual_provider}'.")
                failed_factors.append("Actual post-failover latency/loss did not meet expected SLA recovery criteria.")
                lessons_learned.append(f"Candidate provider '{act_out.actual_provider}' exhibited transient impairment during switchover.")
                recommendation_signals.append(f"Increase verification observation window and re-check candidate SLA before future failovers to '{act_out.actual_provider}'.")
            elif act_out.rollback_status == RollbackStatus.COMPLETED:
                successful_factors.append("Automated rollback engine successfully restored previous network state.")
                failed_factors.append("Primary execution candidate failed post-switchover verification.")
                lessons_learned.append("Closed-loop verification and automatic rollback prevented persistent service outage.")
                recommendation_signals.append("Perform offline interface diagnostics on degraded link before re-attempting automated routing changes.")
            else:
                lessons_learned.append("Execution was simulated or cancelled before verification phase completed.")
                recommendation_signals.append("Ensure live execution authorization is completed to capture post-failover telemetry.")

            # 7. Register Learning Insight into EvidenceRegistry (if context provided)
            if context and hasattr(context, "evidence_registry"):
                reg = context.evidence_registry
                existing_learnings = [e for e in reg.get_by_source("FailoverService") if e.evidence_type == "adaptive_learning"]
                if not existing_learnings:
                    reg.register(
                        source_agent="FailoverService",
                        evidence_type="adaptive_learning",
                        payload={
                            "classification": classification.value,
                            "prediction_error": prediction_error,
                            "decision_quality": quality_score,
                            "quality_label": quality_label,
                            "target_entity": target_entity,
                        },
                        confidence=quality_score,
                        provenance="INFERRED",
                        relationship="SUPPORTING" if quality_score >= 0.70 else ("CONTRADICTING" if quality_score < 0.40 else "NEUTRAL"),
                        affected_entity=target_entity,
                        linked_decision=f"Learning Result: {classification.value} (Quality: {quality_label})",
                        summary=f"Closed-loop decision learning evaluated {classification.value} with quality score {quality_score:.2f} ({quality_label}).",
                        device_id=target_entity,
                    )

            learning_result = AdaptiveDecisionLearningResult(
                learning_id=str(uuid.uuid4()),
                investigation_id=inv_id,
                execution_id=exec_id,
                target_entity=target_entity,
                selected_path=act_out.actual_provider or pred_out.predicted_provider or "ISP-B",
                predicted_outcome=pred_out,
                actual_outcome=act_out,
                learning_classification=classification,
                prediction_error=prediction_error,
                decision_quality_score=quality_score,
                decision_quality_label=quality_label,
                successful_factors=successful_factors,
                failed_factors=failed_factors,
                lessons_learned=lessons_learned,
                future_recommendation_signals=recommendation_signals,
                provenance="INFERRED",
                timestamp=datetime.now(timezone.utc),
                metadata={
                    "classification_precedence_applied": True,
                    "policy_mutation_prevented": True,
                },
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.info(
                f"FailoverService generated decision learning for '{target_entity}' in {elapsed_ms:.2f}ms: "
                f"classification={classification.value}, quality={quality_label} ({quality_score:.2f}), "
                f"prediction_error={prediction_error:.2f}"
            )
            return learning_result
