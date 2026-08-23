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
    ApprovalStatus,
    ExecutionMode,
    ExecutionPlan,
    ExecutionResult,
    ExecutionRisk,
    ExecutionStatus,
    ExecutionStep,
    FailoverApproval,
    FailoverResult,
    RollbackResult,
    RollbackStatus,
    VerificationResult,
    VerificationStatus,
)
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.path_decision.decision_service import PathDecisionService
from agents.path_decision.path_models import PathDecisionResult

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
        path_decision_service: Optional[PathDecisionService] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._approval_manager = approval_manager or ApprovalManager()
        self._validator = validator or PreExecutionValidator(approval_manager=self._approval_manager)
        self._verifier = verifier or PostExecutionVerifier()
        self._rollback_engine = rollback_engine or RollbackEngine()
        self._dry_run_adapter = dry_run_adapter or DryRunExecutionAdapter()
        self._authorized_adapter = authorized_adapter or AuthorizedNetworkAdapter()
        self._path_decision_service = path_decision_service or PathDecisionService()
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
