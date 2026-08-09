"""
Abstract Base Plugin Interface for Hardware Vendor and Protocol Integrations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from agents.core.container import ServiceContainer
from agents.events.event_bus import EventBus
from agents.registry.registry import AgentRegistry


class Plugin(ABC):
    """
    Abstract Base Class for all NOC Copilot plugins.

    Plugins provide integration with hardware vendor telemetry, protocols, and data sources.
    """

    def __init__(
        self,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        registry: Optional[AgentRegistry] = None,
    ) -> None:
        """
        Initialize Plugin instance.

        Args:
            container: ServiceContainer instance for dependency injection.
            event_bus: EventBus instance for event publishing and subscription.
            registry: AgentRegistry instance for registering plugin agents.
        """
        self.container = container or ServiceContainer.get_global()
        self.event_bus = event_bus or EventBus.get_global()
        self.registry = registry or AgentRegistry.get_global()
        self._is_active = False

    @property
    def is_active(self) -> bool:
        """Return True if plugin is currently active and initialized."""
        return self._is_active

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """Unique name identifier of the plugin."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string of the plugin."""
        pass

    @abstractmethod
    def initialize(self) -> None:
        """Initialize plugin resources, subscribe to events, and register services."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Gracefully release plugin resources and subscriptions."""
        pass

    def get_info(self) -> Dict[str, Any]:
        """Return dictionary containing summary information about the plugin."""
        return {
            "plugin_name": self.plugin_name,
            "version": self.version,
            "is_active": self.is_active,
        }
