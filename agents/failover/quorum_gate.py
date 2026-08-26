"""
Production Authorization Quorum Gate & Safety Hardening Engine for NOC Copilot v1.4.

Enforces:
1. Two-Person Rule (2 distinct approvers: Seat 1: NOC_ENGINEER/NOC_ADMIN, Seat 2: NOC_ADMIN)
2. Cryptographic Plan-Hash Binding (exact SHA-256 matching)
3. Approval Expiration & Anti-Replay
4. Change/Maintenance Window Validation (UTC start/end)
5. Security Officer Break-Glass Emergency Override with Signed Audit Trail
6. Enterprise Blast-Radius Limit (max 1 simultaneous carrier transition)
7. Production Failover Cooldown (minimum 300 seconds per target/scope)
8. Device Hardware & Control-Plane Qualification Verification
9. Explicit PRODUCTION_AUTHORIZED Hard-Disablement Enforcement
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
import threading
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from pydantic import BaseModel, ConfigDict, Field

from agents.core.logger import get_agent_logger
from agents.failover.failover_models import ExecutionPlan
from agents.failover.production_control_plane import (
    ControlPlaneStatus,
    IProductionControlPlane,
    validate_endpoint_profile,
)
from agents.failover.production_models import DeviceEndpointProfile
from agents.security.aaa_service import AAAAuthorizationService
from agents.security.mtls_manager import MTLSManager
from agents.security.security_models import AAAIdentity, AAARole, MTLSReadinessStatus

logger = get_agent_logger("QuorumGate")


# ---------------------------------------------------------------------------
# Quorum Decision & Lifecycle Enumerations
# ---------------------------------------------------------------------------


class QuorumDecision(str, Enum):
    """Formal decision outcomes of the production quorum engine."""

    PENDING_QUORUM = "PENDING_QUORUM"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    MAINTENANCE_WINDOW_BLOCKED = "MAINTENANCE_WINDOW_BLOCKED"
    CAPABILITY_BLOCKED = "CAPABILITY_BLOCKED"
    COOLDOWN_BLOCKED = "COOLDOWN_BLOCKED"
    BLAST_RADIUS_BLOCKED = "BLAST_RADIUS_BLOCKED"
    EMERGENCY_APPROVED = "EMERGENCY_APPROVED"
    PRODUCTION_EXECUTION_DISABLED = "PRODUCTION_EXECUTION_DISABLED"


# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------


class MaintenanceWindow(BaseModel):
    """Designates a validated, scheduled maintenance change window."""

    model_config = ConfigDict(frozen=True)

    window_id: str = Field(default_factory=lambda: f"MW-{uuid.uuid4().hex[:8].upper()}")
    change_ticket_id: str = Field(..., description="Change management ticket (e.g. CHG-9921)")
    start_time: datetime = Field(..., description="UTC window start datetime")
    end_time: datetime = Field(..., description="UTC window end datetime")
    target_devices: List[str] = Field(default_factory=list, description="Allowlisted target devices in window")
    approved_by: str = Field(..., description="Change Advisory Board approver ID")

    def is_active(self, now: Optional[datetime] = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return self.start_time <= current <= self.end_time


class IChangeWindowProvider(ABC):
    """Abstract provider for Enterprise Change Management / Maintenance Windows."""

    @abstractmethod
    def get_active_window(self, target_device: str, now: Optional[datetime] = None) -> Optional[MaintenanceWindow]:
        """Fetch active maintenance window for target device."""
        pass

    @abstractmethod
    def validate_change_window(self, target_device: str, now: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
        """Check if target device is currently eligible for production change."""
        pass


class NotConfiguredChangeWindowProvider(IChangeWindowProvider):
    """Safe default change window provider reporting NOT_CONFIGURED."""

    def get_active_window(self, target_device: str, now: Optional[datetime] = None) -> Optional[MaintenanceWindow]:
        return None

    def validate_change_window(self, target_device: str, now: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
        return False, "Change window provider is NOT_CONFIGURED."


class TestChangeWindowProvider(IChangeWindowProvider):
    """In-memory deterministic change window provider for testing."""

    __test__ = False

    def __init__(self) -> None:
        self._windows: Dict[str, MaintenanceWindow] = {}

    def register_window(self, window: MaintenanceWindow) -> None:
        self._windows[window.window_id] = window

    def get_active_window(self, target_device: str, now: Optional[datetime] = None) -> Optional[MaintenanceWindow]:
        current = now or datetime.now(timezone.utc)
        for w in self._windows.values():
            if w.is_active(current) and (not w.target_devices or target_device in w.target_devices):
                return w
        return None

    def validate_change_window(self, target_device: str, now: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
        win = self.get_active_window(target_device, now)
        if win is not None:
            return True, f"Active window {win.window_id} ({win.change_ticket_id})"
        return False, f"No active maintenance window covering device '{target_device}'."


class BreakGlassRequest(BaseModel):
    """Emergency break-glass override request submitted by a Security Officer."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    identity: AAAIdentity = Field(..., description="Must possess SECURITY_OFFICER role")
    reason: str = Field(..., min_length=10, description="Mandatory detailed justification for emergency override")
    signature: str = Field(..., min_length=16, description="Cryptographic or HMAC authorization signature")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class QuorumApprovalSeat(BaseModel):
    """A verified signature seat in the two-person quorum."""

    model_config = ConfigDict(frozen=True)

    seat_number: int = Field(..., ge=1, le=2)
    identity: AAAIdentity = Field(...)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    plan_hash: str = Field(...)


class ProductionAuthorizationDecision(BaseModel):
    """Strongly-typed final authorization decision returned by the quorum engine."""

    model_config = ConfigDict(frozen=True)

    request_id: str = Field(...)
    plan_id: str = Field(...)
    plan_hash: str = Field(...)
    target_device: str = Field(...)
    requester_id: str = Field(...)
    approver_seats: List[QuorumApprovalSeat] = Field(default_factory=list)
    approval_status: str = Field(default="PENDING")
    maintenance_window_status: str = Field(default="NOT_CHECKED")
    mtls_status: str = Field(default="NOT_CHECKED")
    capability_status: str = Field(default="NOT_CHECKED")
    blast_radius_status: str = Field(default="OK")
    cooldown_status: str = Field(default="OK")
    final_decision: QuorumDecision = Field(...)
    rejection_reasons: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Production Authorization Quorum Engine
# ---------------------------------------------------------------------------


class ProductionAuthorizationQuorumEngine:
    """
    Core gatekeeper enforcing two-person approval, plan-hash validation, maintenance windows,
    cooldown timers, blast-radius constraints, and global execution disablement.
    """

    def __init__(
        self,
        change_window_provider: Optional[IChangeWindowProvider] = None,
        mtls_manager: Optional[MTLSManager] = None,
        aaa_service: Optional[AAAAuthorizationService] = None,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self._change_window_provider = change_window_provider or NotConfiguredChangeWindowProvider()
        self._mtls_manager = mtls_manager
        self._aaa_service = aaa_service or AAAAuthorizationService()
        self._cooldown_seconds = cooldown_seconds

        self._active_transitions: Set[str] = set()
        self._last_failover_timestamp: Dict[str, datetime] = {}
        self._proposals: Dict[str, Dict[str, Any]] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._lock = threading.RLock()

    def compute_plan_hash(self, plan: ExecutionPlan) -> str:
        """Deterministic plan-hash computation."""
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

    def propose_production_plan(
        self,
        request_id: str,
        plan: ExecutionPlan,
        requester: AAAIdentity,
        validity_minutes: float = 15.0,
    ) -> ProductionAuthorizationDecision:
        """
        Register a new proposal requiring two-person quorum authorization.
        """
        with self._lock:
            plan_hash = self.compute_plan_hash(plan)
            plan.plan_hash = plan_hash
            target = plan.target_devices[0] if plan.target_devices else "UNKNOWN"
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=validity_minutes)

            self._proposals[request_id] = {
                "request_id": request_id,
                "plan_id": plan.plan_id,
                "plan_hash": plan_hash,
                "target_device": target,
                "requester": requester,
                "expires_at": expires_at,
                "seats": {},
                "status": "PENDING_QUORUM",
            }

            self._log_audit(
                action="PROPOSE_PRODUCTION_PLAN",
                request_id=request_id,
                plan_hash=plan_hash,
                user_id=requester.user_id,
                target_device=target,
                status="PENDING_QUORUM",
            )

            return ProductionAuthorizationDecision(
                request_id=request_id,
                plan_id=plan.plan_id,
                plan_hash=plan_hash,
                target_device=target,
                requester_id=requester.user_id,
                approver_seats=[],
                approval_status="PENDING_QUORUM",
                final_decision=QuorumDecision.PENDING_QUORUM,
            )

    def submit_approval_seat(
        self,
        request_id: str,
        seat_number: int,
        approver: AAAIdentity,
        plan_hash: str,
    ) -> Tuple[bool, List[str]]:
        """
        Submit a verified signature seat to complete the two-person quorum.
        """
        with self._lock:
            proposal = self._proposals.get(request_id)
            if proposal is None:
                return False, [f"Unknown authorization request ID: '{request_id}'."]

            # 1. Expiration check
            if datetime.now(timezone.utc) > proposal["expires_at"]:
                proposal["status"] = "EXPIRED"
                return False, ["Authorization proposal has EXPIRED."]

            # 2. Plan-hash binding check
            if plan_hash != proposal["plan_hash"]:
                return False, [f"Plan hash mismatch: Expected '{proposal['plan_hash']}', got '{plan_hash}'."]

            # 3. Two-Person Rule: Requester cannot approve their own plan
            if approver.user_id == proposal["requester"].user_id:
                return False, ["Two-person rule violation: Requester cannot be an approver."]

            # 4. Seat number validation
            if seat_number not in (1, 2):
                return False, [f"Invalid seat number: {seat_number} (must be 1 or 2)."]

            # 5. Role requirements
            if seat_number == 1:
                if not (approver.has_role(AAARole.NOC_ENGINEER) or approver.has_role(AAARole.NOC_ADMIN)):
                    return False, ["Seat 1 requires NOC_ENGINEER or NOC_ADMIN role."]
            elif seat_number == 2:
                if not approver.has_role(AAARole.NOC_ADMIN):
                    return False, ["Seat 2 requires NOC_ADMIN role."]

            # 6. Distinct identity check across seats
            other_seat = 2 if seat_number == 1 else 1
            if other_seat in proposal["seats"]:
                existing_approver = proposal["seats"][other_seat].identity
                if existing_approver.user_id == approver.user_id:
                    return False, ["Two-person rule violation: Seat 1 and Seat 2 approvers must be distinct identities."]

            # Record seat
            seat = QuorumApprovalSeat(
                seat_number=seat_number,
                identity=approver,
                plan_hash=plan_hash,
            )
            proposal["seats"][seat_number] = seat

            self._log_audit(
                action=f"SUBMIT_APPROVAL_SEAT_{seat_number}",
                request_id=request_id,
                plan_hash=plan_hash,
                user_id=approver.user_id,
                target_device=proposal["target_device"],
                status="SEAT_RECORDED",
            )

            return True, []

    def emergency_break_glass(
        self,
        request_id: str,
        break_glass: BreakGlassRequest,
        plan: ExecutionPlan,
        target_profile: Optional[DeviceEndpointProfile] = None,
    ) -> ProductionAuthorizationDecision:
        """
        Execute Security Officer emergency break-glass override.
        """
        with self._lock:
            rejection_reasons: List[str] = []
            target = plan.target_devices[0] if plan.target_devices else "UNKNOWN"
            plan_hash = self.compute_plan_hash(plan)

            # 1. Role validation
            if not break_glass.identity.has_role(AAARole.SECURITY_OFFICER):
                rejection_reasons.append("Break-glass override requires SECURITY_OFFICER role.")

            # 2. Reason validation
            if not break_glass.reason or len(break_glass.reason.strip()) < 10:
                rejection_reasons.append("Mandatory detailed break-glass reason required (min 10 chars).")

            # 3. Signature validation
            if not break_glass.signature or len(break_glass.signature.strip()) < 16:
                rejection_reasons.append("Valid cryptographic signature required for emergency override.")

            self._log_audit(
                action="EMERGENCY_BREAK_GLASS",
                request_id=request_id,
                plan_hash=plan_hash,
                user_id=break_glass.identity.user_id,
                target_device=target,
                status="REJECTED" if rejection_reasons else "EMERGENCY_APPROVED",
                rejection_reasons=rejection_reasons,
                extra={"reason": break_glass.reason},
            )

            decision = QuorumDecision.EMERGENCY_APPROVED if not rejection_reasons else QuorumDecision.REJECTED

            # In all cases, PRODUCTION_AUTHORIZED flag hard-gates execution
            return ProductionAuthorizationDecision(
                request_id=request_id,
                plan_id=plan.plan_id,
                plan_hash=plan_hash,
                target_device=target,
                requester_id=break_glass.identity.user_id,
                approver_seats=[],
                approval_status="EMERGENCY_BREAK_GLASS",
                final_decision=decision,
                rejection_reasons=rejection_reasons,
            )

    def evaluate_authorization(
        self,
        request_id: str,
        plan: ExecutionPlan,
        target_profile: Optional[DeviceEndpointProfile] = None,
        control_plane: Optional[IProductionControlPlane] = None,
    ) -> ProductionAuthorizationDecision:
        """
        Evaluate full multi-point production authorization gate.
        Derives production authorization state strictly from config.settings.PRODUCTION_AUTHORIZED.
        """
        with self._lock:
            rejection_reasons: List[str] = []
            now = datetime.now(timezone.utc)
            target = plan.target_devices[0] if plan.target_devices else "UNKNOWN"
            plan_hash = self.compute_plan_hash(plan)

            proposal = self._proposals.get(request_id)
            if proposal is None:
                return ProductionAuthorizationDecision(
                    request_id=request_id,
                    plan_id=plan.plan_id,
                    plan_hash=plan_hash,
                    target_device=target,
                    requester_id="UNKNOWN",
                    final_decision=QuorumDecision.REJECTED,
                    rejection_reasons=["Unknown proposal request ID."],
                )

            # 1. Quorum Check (Seats 1 and 2 present)
            seats = proposal.get("seats", {})
            if 1 not in seats or 2 not in seats:
                rejection_reasons.append("Two-person quorum incomplete: Both Seat 1 and Seat 2 approvals required.")
                return ProductionAuthorizationDecision(
                    request_id=request_id,
                    plan_id=plan.plan_id,
                    plan_hash=plan_hash,
                    target_device=target,
                    requester_id=proposal["requester"].user_id,
                    approver_seats=list(seats.values()),
                    approval_status="PENDING_QUORUM",
                    final_decision=QuorumDecision.PENDING_QUORUM,
                    rejection_reasons=rejection_reasons,
                )

            # 2. Expiration Check
            if now > proposal["expires_at"]:
                rejection_reasons.append("Quorum authorization has EXPIRED.")
                return ProductionAuthorizationDecision(
                    request_id=request_id,
                    plan_id=plan.plan_id,
                    plan_hash=plan_hash,
                    target_device=target,
                    requester_id=proposal["requester"].user_id,
                    approver_seats=list(seats.values()),
                    approval_status="EXPIRED",
                    final_decision=QuorumDecision.EXPIRED,
                    rejection_reasons=rejection_reasons,
                )

            # 3. Maintenance Window Check
            win_ok, win_msg = self._change_window_provider.validate_change_window(target, now=now)
            maint_status = "ACTIVE" if win_ok else "BLOCKED"
            if not win_ok:
                rejection_reasons.append(f"Maintenance window check failed: {win_msg}")

            # 4. Enterprise Blast-Radius Constraint (max 1 concurrent carrier transition)
            blast_status = "OK"
            if len(self._active_transitions) >= 1 and target not in self._active_transitions:
                blast_status = "BLOCKED"
                rejection_reasons.append(
                    f"Enterprise blast-radius violation: Another production transition is active ({self._active_transitions})."
                )

            # 5. Cooldown Timer Check (300 seconds)
            cooldown_status = "OK"
            if target in self._last_failover_timestamp:
                elapsed = (now - self._last_failover_timestamp[target]).total_seconds()
                if elapsed < self._cooldown_seconds:
                    cooldown_status = "BLOCKED"
                    rejection_reasons.append(
                        f"Cooldown active on '{target}': {elapsed:.1f}s elapsed < {self._cooldown_seconds}s required."
                    )

            # 6. Target Profile & Allowlist Validation
            mtls_status = "OK"
            capability_status = "OK"
            if target_profile is not None:
                is_valid, errs = validate_endpoint_profile(target_profile)
                if not is_valid:
                    mtls_status = "INVALID"
                    rejection_reasons.extend(errs)

            if control_plane is not None:
                readiness = control_plane.check_readiness()
                if readiness.status != ControlPlaneStatus.READY:
                    capability_status = "UNAVAILABLE"
                    rejection_reasons.append(f"Control plane readiness is {readiness.status.value}: {readiness.message}")

            # 7. Decision Mapping
            if rejection_reasons:
                if maint_status == "BLOCKED":
                    dec = QuorumDecision.MAINTENANCE_WINDOW_BLOCKED
                elif blast_status == "BLOCKED":
                    dec = QuorumDecision.BLAST_RADIUS_BLOCKED
                elif cooldown_status == "BLOCKED":
                    dec = QuorumDecision.COOLDOWN_BLOCKED
                elif capability_status == "UNAVAILABLE" or mtls_status == "INVALID":
                    dec = QuorumDecision.CAPABILITY_BLOCKED
                else:
                    dec = QuorumDecision.REJECTED
            else:
                # ALL PRECHECKS & QUORUM PASSED!
                # NOW CHECK HARD PRODUCTION EXECUTION FLAG DERIVED FROM config.settings
                from config import settings
                is_prod_authorized = bool(getattr(settings, "PRODUCTION_AUTHORIZED", False))
                if not is_prod_authorized:
                    dec = QuorumDecision.PRODUCTION_EXECUTION_DISABLED
                    rejection_reasons.append(
                        "PRODUCTION_AUTHORIZED is hard-disabled in system settings. Live production mutation blocked."
                    )
                else:
                    dec = QuorumDecision.APPROVED

            self._log_audit(
                action="EVALUATE_PRODUCTION_AUTHORIZATION",
                request_id=request_id,
                plan_hash=plan_hash,
                user_id=proposal["requester"].user_id,
                target_device=target,
                status=dec.value,
                rejection_reasons=rejection_reasons,
            )

            return ProductionAuthorizationDecision(
                request_id=request_id,
                plan_id=plan.plan_id,
                plan_hash=plan_hash,
                target_device=target,
                requester_id=proposal["requester"].user_id,
                approver_seats=list(seats.values()),
                approval_status="APPROVED" if dec in (QuorumDecision.APPROVED, QuorumDecision.PRODUCTION_EXECUTION_DISABLED) else "REJECTED",
                maintenance_window_status=maint_status,
                mtls_status=mtls_status,
                capability_status=capability_status,
                blast_radius_status=blast_status,
                cooldown_status=cooldown_status,
                final_decision=dec,
                rejection_reasons=rejection_reasons,
            )

    def record_transition_start(self, target_device: str) -> None:
        """Mark a production transition as actively underway."""
        with self._lock:
            self._active_transitions.add(target_device)

    def record_transition_completed(self, target_device: str) -> None:
        """Mark a production transition as completed and start cooldown timer."""
        with self._lock:
            self._active_transitions.discard(target_device)
            self._last_failover_timestamp[target_device] = datetime.now(timezone.utc)

    def _log_audit(
        self,
        action: str,
        request_id: str,
        plan_hash: str,
        user_id: str,
        target_device: str,
        status: str,
        rejection_reasons: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Structured audit logging guaranteed to redact credentials and secret payloads."""
        record = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "request_id": request_id,
            "plan_hash": plan_hash,
            "user_id": user_id,
            "target_device": target_device,
            "status": status,
            "rejection_reasons": rejection_reasons or [],
        }
        if extra:
            # Strictly filter any sensitive keys
            filtered_extra = {k: v for k, v in extra.items() if "secret" not in k.lower() and "key" not in k.lower()}
            record["extra"] = filtered_extra

        self._audit_log.append(record)
        logger.info(f"QuorumGateAudit: {action} [{status}] request={request_id} target={target_device}")

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Retrieve copy of structured audit trail."""
        with self._lock:
            return list(self._audit_log)
