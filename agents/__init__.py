"""
Atomic Agents Framework Package Initialization.

Provides production-grade AI orchestration, abstract agent base classes,
event bus, dependency injection container, thread-safe registry, and shared domain schemas.
"""

__version__ = "1.4.0-rc1"

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import (
    AgentError,
    ConfigurationError,
    ContainerError,
    EventError,
    ExecutionError,
    RegistrationError,
    ValidationError,
)
from agents.core.logger import (
    AgentLogFormatter,
    get_agent_logger,
    log_execution_event,
)
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.events.publisher import Publisher
from agents.events.subscriber import Subscriber, SubscriberSubscription
from agents.interfaces.agent_interface import IAgent
from agents.orchestrator.orchestrator import AgentOrchestrator
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import (
    AgentMetadata,
    AgentMetrics,
    AgentState,
    CapabilityFlags,
    DeviceHealth,
    ExecutionContext,
    Incident,
    PredictionResult,
    Recommendation,
    TelemetryPacket,
    TopologyState,
)

from agents.path_decision.path_decision_agent import PathDecisionAgent
from agents.path_decision.decision_service import PathDecisionService
from agents.path_decision.path_models import PathCandidate, PathDecisionResult, FailoverRecommendation

from agents.failover.failover_agent import FailoverAgent
from agents.failover.failover_service import FailoverService
from agents.failover.approval_manager import ApprovalManager
from agents.failover.pre_execution_validator import PreExecutionValidator
from agents.failover.post_execution_verifier import PostExecutionVerifier
from agents.failover.rollback_engine import RollbackEngine
from agents.failover.failover_models import FailoverApproval, ExecutionPlan, ExecutionResult, VerificationResult, RollbackResult, FailoverResult

from agents.adaptive_failover.adaptive_failover_agent import AdaptiveFailoverAgent
from agents.adaptive_failover.adaptive_failover_service import AdaptiveFailoverService
from agents.adaptive_failover.provider_monitor import ProviderMonitor
from agents.adaptive_failover.degradation_detector import DegradationDetector
from agents.adaptive_failover.stability_engine import StabilityEngine
from agents.adaptive_failover.failback_engine import FailbackEngine
from agents.adaptive_failover.adaptive_models import AdaptiveFailoverResult

from agents.federated_intelligence.federated_intelligence_agent import FederatedIntelligenceAgent
from agents.federated_intelligence.federated_intelligence_service import FederatedIntelligenceService
from agents.federated_intelligence.privacy_sanitizer import PrivacySanitizer
from agents.federated_intelligence.crypto_signer import CryptoSigner
from agents.federated_intelligence.bundle_exporter import BundleExporter
from agents.federated_intelligence.bundle_importer import BundleImporter
from agents.federated_intelligence.federated_models import FederatedKnowledgeBundle, ImportValidationResult, ExportBundleResult

__all__ = [
    # Base and Interfaces
    "BaseAgent",
    "IAgent",
    # Registry and Orchestrator
    "AgentRegistry",
    "AgentOrchestrator",
    # Path Decision Engine
    "PathDecisionAgent",
    "PathDecisionService",
    "PathCandidate",
    "PathDecisionResult",
    "FailoverRecommendation",
    # Failover Execution & Closed-Loop Verification
    "FailoverAgent",
    "FailoverService",
    "ApprovalManager",
    "PreExecutionValidator",
    "PostExecutionVerifier",
    "RollbackEngine",
    "FailoverApproval",
    "ExecutionPlan",
    "ExecutionResult",
    "VerificationResult",
    "RollbackResult",
    "FailoverResult",
    # Adaptive Failover & Stability Intelligence
    "AdaptiveFailoverAgent",
    "AdaptiveFailoverService",
    "ProviderMonitor",
    "DegradationDetector",
    "StabilityEngine",
    "FailbackEngine",
    "AdaptiveFailoverResult",
    # Air-Gapped Federated Intelligence & Signed Knowledge Exchange
    "FederatedIntelligenceAgent",
    "FederatedIntelligenceService",
    "PrivacySanitizer",
    "CryptoSigner",
    "BundleExporter",
    "BundleImporter",
    "FederatedKnowledgeBundle",
    "ImportValidationResult",
    "ExportBundleResult",
    "RollbackResult",
    "FailoverResult",
    # Core Infrastructure
    "ServiceContainer",
    "AgentLogFormatter",
    "get_agent_logger",
    "log_execution_event",
    # Events
    "Event",
    "EventBus",
    "Publisher",
    "Subscriber",
    "SubscriberSubscription",
    # Exceptions
    "AgentError",
    "RegistrationError",
    "ExecutionError",
    "ValidationError",
    "ConfigurationError",
    "EventError",
    "ContainerError",
    # Schemas
    "AgentState",
    "CapabilityFlags",
    "AgentMetadata",
    "AgentMetrics",
    "TelemetryPacket",
    "PredictionResult",
    "DeviceHealth",
    "Incident",
    "Recommendation",
    "TopologyState",
    "ExecutionContext",
]

