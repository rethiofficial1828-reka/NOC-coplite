"""
Failover Models Module for Enterprise Controlled Failover Execution & Closed-Loop Verification Engine.

Defines strongly-typed Pydantic V2 domain models and enums representing failover execution modes,
approval lifecycles, execution status, pre-execution checks, execution plans/steps/results,
closed-loop post-execution verification checks, automatic rollback results, and complete audit bundles.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ExecutionMode(str, Enum):
    """Execution mode taxonomy."""

    DRY_RUN = "DRY_RUN"
    SIMULATION = "SIMULATION"
    APPROVED_EXECUTION = "APPROVED_EXECUTION"


class ApprovalStatus(str, Enum):
    """Lifecycle status for human operator approval."""

    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    INVALIDATED = "INVALIDATED"


class ExecutionStatus(str, Enum):
    """Detailed execution status taxonomy."""

    NOT_STARTED = "NOT_STARTED"
    PRECHECK_FAILED = "PRECHECK_FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


class VerificationStatus(str, Enum):
    """Closed-loop post-execution verification status."""

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    PASSED = "PASSED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    TIMEOUT = "TIMEOUT"


class RollbackStatus(str, Enum):
    """Automatic rollback lifecycle status."""

    NOT_REQUIRED = "NOT_REQUIRED"
    READY = "READY"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RestorationStatus(str, Enum):
    """State restoration status taxonomy."""

    RESTORED = "RESTORED"
    FAILED = "FAILED"
    NOT_RESTORED = "NOT_RESTORED"


class ExecutionRisk(str, Enum):
    """Risk severity classification for execution plan."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FailureReason(str, Enum):
    """Structured failure reason classification."""

    STALE_TELEMETRY = "stale_telemetry"
    INSUFFICIENT_CONFIDENCE = "insufficient_confidence"
    TRUST_BLOCKED = "trust_blocked"
    BLAST_RADIUS_TOO_HIGH = "blast_radius_too_high"
    APPROVAL_MISSING = "approval_missing"
    APPROVAL_EXPIRED = "approval_expired"
    TARGET_UNREACHABLE = "target_unreachable"
    PRECHECK_FAILED = "precheck_failed"
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    ROLLBACK_FAILED = "rollback_failed"
    POLICY_VIOLATION = "policy_violation"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Core Domain Models
# ---------------------------------------------------------------------------


class FailoverApproval(BaseModel):
    """Formal operator authorization record for network execution."""

    model_config = ConfigDict(frozen=False)

    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str = Field(...)
    request_id: str = Field(...)
    operator_id: str = Field(...)
    approved_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)
    approved_execution_plan_hash: str = Field(...)
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING_APPROVAL)
    notes: str = Field(default="")


class PreExecutionCheck(BaseModel):
    """Validation check evaluated immediately prior to execution."""

    model_config = ConfigDict(frozen=False)

    check_name: str = Field(...)
    status: str = Field(default="PASSED", description="PASSED, FAILED, or WARNING")
    expected: str = Field(...)
    observed: str = Field(...)
    evidence_reference: Optional[str] = Field(default=None)
    severity: str = Field(default="HIGH")
    message: str = Field(default="")


class ExecutionStep(BaseModel):
    """Typed, controlled step within an ExecutionPlan (NO arbitrary shell commands)."""

    model_config = ConfigDict(frozen=False)

    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int = Field(default=1)
    adapter: str = Field(default="DryRunExecutionAdapter")
    target: str = Field(...)
    action_type: str = Field(..., description="FAILOVER_PROVIDER, FAILBACK_PROVIDER, ENABLE_BACKUP_PATH, etc.")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Validated parameter payload")
    timeout_sec: float = Field(default=30.0)
    reversible: bool = Field(default=True)
    rollback_step_id: Optional[str] = Field(default=None)


class ExecutionPlan(BaseModel):
    """Structured execution plan generated from an approved path decision."""

    model_config = ConfigDict(frozen=False)

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str = Field(...)
    source_path: str = Field(...)
    destination_path: str = Field(...)
    target_devices: List[str] = Field(default_factory=list)
    steps: List[ExecutionStep] = Field(default_factory=list)
    expected_changes: Dict[str, Any] = Field(default_factory=dict)
    expected_metrics: Dict[str, float] = Field(default_factory=dict)
    rollback_plan: List[ExecutionStep] = Field(default_factory=list)
    risk: ExecutionRisk = Field(default=ExecutionRisk.LOW)
    blast_radius: str = Field(default="LOW")
    plan_hash: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExecutionResult(BaseModel):
    """Result of an execution plan run through an authorized adapter."""

    model_config = ConfigDict(frozen=False)

    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    plan_id: str = Field(...)
    status: ExecutionStatus = Field(default=ExecutionStatus.NOT_STARTED)
    mode: ExecutionMode = Field(default=ExecutionMode.DRY_RUN)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)
    executed_steps: List[str] = Field(default_factory=list)
    failed_steps: List[str] = Field(default_factory=list)
    adapter_results: Dict[str, Any] = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)


class VerificationCheck(BaseModel):
    """Post-execution metric or health verification check."""

    model_config = ConfigDict(frozen=False)

    metric: str = Field(...)
    expected_range: str = Field(...)
    observed_value: float = Field(...)
    status: str = Field(default="PASSED", description="PASSED, FAILED, or WARNING")
    evidence_reference: Optional[str] = Field(default=None)


class VerificationResult(BaseModel):
    """Closed-loop post-execution verification outcome."""

    model_config = ConfigDict(frozen=False)

    verification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str = Field(...)
    status: VerificationStatus = Field(default=VerificationStatus.NOT_STARTED)
    checks: List[VerificationCheck] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    service_health: str = Field(default="HEALTHY")
    path_health: str = Field(default="HEALTHY")
    incident_state: str = Field(default="RESOLVED")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RollbackResult(BaseModel):
    """Outcome of an automatic or manual rollback procedure."""

    model_config = ConfigDict(frozen=False)

    rollback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    execution_id: str = Field(...)
    status: RollbackStatus = Field(default=RollbackStatus.NOT_REQUIRED)
    restored_state: Dict[str, Any] = Field(default_factory=dict)
    verification: Optional[VerificationResult] = Field(default=None)
    errors: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def restoration_status(self) -> RestorationStatus:
        """Compatibility property mapping RollbackStatus to RestorationStatus."""
        if self.status == RollbackStatus.COMPLETED:
            return RestorationStatus.RESTORED
        return RestorationStatus.FAILED


class FailoverResult(BaseModel):
    """Complete auditable lifecycle record for a controlled failover run."""

    model_config = ConfigDict(frozen=False)

    failover_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(...)
    decision_id: str = Field(...)
    approval: Optional[FailoverApproval] = Field(default=None)
    prechecks: List[PreExecutionCheck] = Field(default_factory=list)
    execution_plan: Optional[ExecutionPlan] = Field(default=None)
    execution_result: Optional[ExecutionResult] = Field(default=None)
    verification_result: Optional[VerificationResult] = Field(default=None)
    rollback_result: Optional[RollbackResult] = Field(default=None)
    final_status: ExecutionStatus = Field(default=ExecutionStatus.NOT_STARTED)
    audit_reference: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
