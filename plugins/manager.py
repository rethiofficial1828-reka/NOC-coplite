"""
Plugin Manager for Plugin Lifecycle Management and Service Registration.
"""

import threading
from typing import Dict, List, Optional, Type

from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger
from agents.events.event_bus import EventBus
from agents.registry.registry import AgentRegistry
from plugins.base import Plugin
from plugins.loader import PluginLoader

logger = get_agent_logger("PluginManager")


class PluginManager:
    """
    Manager for registering, initializing, and shutting down framework plugins.
    """

    _global_instance: Optional["PluginManager"] = None
    _global_lock = threading.Lock()

    def __init__(
        self,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        registry: Optional[AgentRegistry] = None,
    ) -> None:
        """
        Initialize PluginManager.

        Args:
            container: ServiceContainer instance.
            event_bus: EventBus instance.
            registry: AgentRegistry instance.
        """
        self._container = container or ServiceContainer.get_global()
        self._event_bus = event_bus or EventBus.get_global()
        self._registry = registry or AgentRegistry.get_global()
        self._plugins: Dict[str, Plugin] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "PluginManager":
        """Get or create global singleton PluginManager instance."""
        if cls._global_instance is None:
            with cls._global_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    def register_plugin(self, plugin: Plugin) -> None:
        """
        Register and initialize a plugin instance.

        Args:
            plugin: Instance of Plugin subclass.
        """
        name = plugin.plugin_name
        with self._lock:
            if name in self._plugins:
                logger.warning(f"Plugin '{name}' is already registered. Skipping.")
                return

            try:
                plugin.initialize()
                plugin._is_active = True
                self._plugins[name] = plugin
                logger.info(f"Successfully registered and initialized plugin '{name}' (v{plugin.version})")
            except Exception as e:
                logger.error(f"Failed to initialize plugin '{name}': {e}", exc_info=True)
                raise

    def load_and_register_from_directory(self, directory_path: str) -> List[str]:
        """
        Discover, instantiate, and register all plugins found in a directory.

        Args:
            directory_path: Directory path to scan for plugins.

        Returns:
            List of successfully registered plugin names.
        """
        plugin_classes: List[Type[Plugin]] = PluginLoader.discover_plugins_in_directory(directory_path)
        registered_names: List[str] = []

        for p_cls in plugin_classes:
            try:
                instance = p_cls(
                    container=self._container,
                    event_bus=self._event_bus,
                    registry=self._registry,
                )
                self.register_plugin(instance)
                registered_names.append(instance.plugin_name)
            except Exception as e:
                logger.error(f"Error registering plugin class '{p_cls.__name__}': {e}", exc_info=True)

        return registered_names

    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """Get a registered plugin instance by name."""
        with self._lock:
            return self._plugins.get(plugin_name)

    def list_plugins(self) -> Dict[str, Dict[str, str]]:
        """Return dict of registered plugins and their metadata."""
        with self._lock:
            return {
                name: {
                    "plugin_name": p.plugin_name,
                    "version": p.version,
                    "is_active": str(p.is_active),
                }
                for name, p in self._plugins.items()
            }

    def shutdown_all(self) -> None:
        """Shutdown all active plugins."""
        with self._lock:
            for name, plugin in list(self._plugins.items()):
                try:
                    if plugin.is_active:
                        plugin.shutdown()
                        plugin._is_active = False
                    logger.info(f"Shutdown plugin '{name}'")
                except Exception as e:
                    logger.error(f"Error shutting down plugin '{name}': {e}", exc_info=True)
            self._plugins.clear()
