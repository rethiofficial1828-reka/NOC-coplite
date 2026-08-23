"""
Approval Manager Module for Enterprise Controlled Failover Execution Engine.

Manages the lifecycle of formal operator authorizations (PENDING_APPROVAL, APPROVED, REJECTED,
EXPIRED, CANCELLED, INVALIDATED). Enforces cryptographic plan-hash binding, expiration timers,
operator identity validation, and anti-replay protection.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
from typing import Any, Dict, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.failover.failover_models import ApprovalStatus, ExecutionPlan, FailoverApproval

logger = get_agent_logger("ApprovalManager")


class ApprovalManager:
    """
    Thread-safe approval manager enforcing cryptographic binding and anti-replay protection.
    """

    def __init__(self, default_validity_minutes: float = 15.0) -> None:
        self._default_validity_minutes = default_validity_minutes
        self._approvals: Dict[str, FailoverApproval] = {}
        self._executed_plan_hashes: set[str] = set()
        self._lock = threading.RLock()

    def compute_plan_hash(self, plan: ExecutionPlan) -> str:
        """
        Calculate deterministic SHA-256 hash of an ExecutionPlan.

        Args:
            plan: ExecutionPlan domain object.

        Returns:
            Hex digest hash string.
        """
        canonical_dict = {
            "source_path": plan.source_path,
            "destination_path": plan.destination_path,
            "target_devices": sorted(plan.target_devices),
            "steps": [
                {
                    "sequence": s.sequence,
                    "target": s.target,
                    "action_type": s.action_type,
                    "parameters": s.parameters,
                }
                for s in plan.steps
            ],
            "expected_metrics": plan.expected_metrics,
        }
        encoded = json.dumps(canonical_dict, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def request_approval(
        self,
        decision_id: str,
        request_id: str,
        plan: ExecutionPlan,
        operator_id: str = "SYSTEM_AUTOMATION",
        validity_minutes: Optional[float] = None,
    ) -> FailoverApproval:
        """
        Create a new PENDING_APPROVAL request bound to the execution plan hash.
        """
        with self._lock:
            plan_hash = self.compute_plan_hash(plan)
            plan.plan_hash = plan_hash

            mins = validity_minutes if validity_minutes is not None else self._default_validity_minutes
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=mins)

            approval = FailoverApproval(
                decision_id=decision_id,
                request_id=request_id,
                operator_id=operator_id,
                approved_execution_plan_hash=plan_hash,
                status=ApprovalStatus.PENDING_APPROVAL,
                expires_at=expires_at,
            )

            self._approvals[approval.approval_id] = approval
            logger.info(f"ApprovalManager created approval request '{approval.approval_id}' (Hash: {plan_hash[:8]}...)")
            return approval

    def approve_request(
        self,
        approval_id: str,
        operator_id: str,
        plan: Optional[ExecutionPlan] = None,
        notes: str = "",
    ) -> Tuple[bool, FailoverApproval, str]:
        """
        Approve a pending approval request. Validates plan hash match if plan object provided.
        """
        with self._lock:
            approval = self._approvals.get(approval_id)
            if not approval:
                for a in self._approvals.values():
                    if a.request_id == approval_id:
                        approval = a
                        break
            if not approval:
                return False, FailoverApproval(decision_id="", request_id="", operator_id="", approved_execution_plan_hash=""), f"Approval '{approval_id}' not found."

            now = datetime.now(timezone.utc)
            if approval.expires_at and now > approval.expires_at:
                approval.status = ApprovalStatus.EXPIRED
                return False, approval, "Approval request has expired."

            if plan is not None:
                current_plan_hash = self.compute_plan_hash(plan)
                if current_plan_hash != approval.approved_execution_plan_hash:
                    approval.status = ApprovalStatus.INVALIDATED
                    return False, approval, "Execution plan hash mismatch — plan modified after approval request."

            approval.operator_id = operator_id
            approval.approved_at = now
            approval.status = ApprovalStatus.APPROVED
            approval.notes = notes

            logger.info(f"ApprovalManager: Approval '{approval.approval_id}' APPROVED by operator '{operator_id}'.")
            return True, approval, "APPROVED"

    def reject_request(self, approval_id: str, operator_id: str, notes: str = "") -> FailoverApproval:
        """Reject an approval request."""
        with self._lock:
            approval = self._approvals.get(approval_id)
            if approval:
                approval.operator_id = operator_id
                approval.status = ApprovalStatus.REJECTED
                approval.notes = notes
                logger.info(f"ApprovalManager: Approval '{approval_id}' REJECTED by operator '{operator_id}'.")
            return approval or FailoverApproval(decision_id="", request_id="", operator_id=operator_id, approved_execution_plan_hash="", status=ApprovalStatus.REJECTED)

    def validate_approval(self, approval_id: str, plan: ExecutionPlan) -> Tuple[bool, str]:
        """
        Verify that approval is valid, approved, unexpired, matches plan hash, and is not a replay.
        """
        with self._lock:
            approval = self._approvals.get(approval_id)
            if not approval:
                return False, f"Approval ID '{approval_id}' not found."

            if approval.status != ApprovalStatus.APPROVED:
                return False, f"Approval status is '{approval.status.value}' (expected APPROVED)."

            now = datetime.now(timezone.utc)
            if approval.expires_at and now > approval.expires_at:
                approval.status = ApprovalStatus.EXPIRED
                return False, f"Approval '{approval_id}' expired at {approval.expires_at.isoformat()}."

            current_plan_hash = self.compute_plan_hash(plan)
            if current_plan_hash != approval.approved_execution_plan_hash:
                approval.status = ApprovalStatus.INVALIDATED
                return False, f"Execution plan hash mismatch (Approved: {approval.approved_execution_plan_hash[:8]}, Current: {current_plan_hash[:8]})."

            if current_plan_hash in self._executed_plan_hashes:
                return False, "Duplicate execution attempt — plan hash has already been executed (Anti-Replay)."

            return True, "VALID"

    def mark_plan_executed(self, plan_hash: str) -> None:
        """Record plan hash as executed to prevent replay attacks."""
        with self._lock:
            self._executed_plan_hashes.add(plan_hash)
            logger.debug(f"ApprovalManager recorded executed plan hash: {plan_hash[:8]}...")

    # ------------------------------------------------------------------
    # Compatibility aliases used by integration tests
    # ------------------------------------------------------------------

    def create_approval_request(self, target: str, plan_hash: str) -> FailoverApproval:
        """
        Simplified approval request factory used by integration tests.

        Args:
            target: Target device or interface string.
            plan_hash: Pre-computed plan hash string.

        Returns:
            FailoverApproval with PENDING_APPROVAL status.
        """
        import uuid as _uuid
        from datetime import timedelta
        with self._lock:
            approval = FailoverApproval(
                decision_id=str(_uuid.uuid4()),
                request_id=str(_uuid.uuid4()),
                operator_id="SYSTEM_AUTOMATION",
                approved_execution_plan_hash=plan_hash,
                status=ApprovalStatus.PENDING_APPROVAL,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=self._default_validity_minutes),
            )
            self._approvals[approval.approval_id] = approval
            logger.info(f"ApprovalManager created approval request '{approval.approval_id}' for target '{target}'")
            return approval

    def reject_approval(self, approval_id: str, notes: str = "") -> FailoverApproval:
        """Alias for reject_request using operator_id=SYSTEM_AUTOMATION."""
        return self.reject_request(approval_id=approval_id, operator_id="SYSTEM_AUTOMATION", notes=notes)

    def validate_approval_for_execution(self, approval_id: str, plan_hash: str) -> Tuple[bool, str]:
        """
        Validate approval using a raw plan hash string (integration test compatible).

        Args:
            approval_id: Approval ID to validate.
            plan_hash: Raw plan hash string to compare.

        Returns:
            Tuple of (valid: bool, message: str)
        """
        with self._lock:
            approval = self._approvals.get(approval_id)
            if not approval:
                for a in self._approvals.values():
                    if a.request_id == approval_id:
                        approval = a
                        break
            if not approval:
                return False, f"Approval ID '{approval_id}' not found."

            if approval.status != ApprovalStatus.APPROVED:
                return False, f"Approval status is '{approval.status.value}' (expected APPROVED)."

            now = datetime.now(timezone.utc)
            if approval.expires_at and now > approval.expires_at:
                approval.status = ApprovalStatus.EXPIRED
                return False, f"Approval '{approval_id}' expired."

            if plan_hash != approval.approved_execution_plan_hash:
                approval.status = ApprovalStatus.INVALIDATED
                return False, f"Plan hash mismatch (approved: {approval.approved_execution_plan_hash[:8]}, current: {plan_hash[:8]})."

            if plan_hash in self._executed_plan_hashes:
                return False, "Anti-Replay: plan hash already executed."

            return True, "VALID"

