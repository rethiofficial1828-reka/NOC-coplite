"""
Failover Package Entrypoint for NOC Copilot.

Exports atomic agent, domain services, approval manager, adapters, prechecks, verifier,
rollback engine, and domain models for Sprint 18 Controlled Failover Execution Engine.
"""

from agents.failover.approval_manager import ApprovalManager
from agents.failover.authorized_execution_adapter import AuthorizedNetworkAdapter
from agents.failover.dry_run_adapter import DryRunExecutionAdapter
from agents.failover.execution_adapter import IExecutionAdapter
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
    FailureReason,
    LearningClassification,
    PreExecutionCheck,
    PredictedOutcome,
    RollbackResult,
    RollbackStatus,
    VerificationCheck,
    VerificationResult,
    VerificationStatus,
)
from agents.failover.failover_service import FailoverService
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.rollback_engine import RollbackEngine

__all__ = [
    "FailoverAgent",
    "FailoverService",
    "ApprovalManager",
    "PreExecutionValidator",
    "IExecutionAdapter",
    "DryRunExecutionAdapter",
    "AuthorizedNetworkAdapter",
    "PostExecutionVerifier",
    "RollbackEngine",
    "ExecutionMode",
    "ApprovalStatus",
    "ExecutionStatus",
    "VerificationStatus",
    "RollbackStatus",
    "ExecutionRisk",
    "FailureReason",
    "FailoverApproval",
    "PreExecutionCheck",
    "ExecutionStep",
    "ExecutionPlan",
    "ExecutionResult",
    "VerificationCheck",
    "VerificationResult",
    "RollbackResult",
    "FailoverResult",
    "LearningClassification",
    "PredictedOutcome",
    "ActualOutcome",
    "AdaptiveDecisionLearningResult",
]
