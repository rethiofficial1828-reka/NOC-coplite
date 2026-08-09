"""
Atomic Agents Framework Package Initialization.

Provides production-grade AI orchestration, abstract agent base classes,
event bus, dependency injection container, thread-safe registry, and shared domain schemas.
"""

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

__all__ = [
    # Base and Interfaces
    "BaseAgent",
    "IAgent",
    # Registry and Orchestrator
    "AgentRegistry",
    "AgentOrchestrator",
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
