"""
Plugins Package Initialization.

Provides plugin architecture foundation for protocol and hardware vendor integrations.
"""

from plugins.base import Plugin
from plugins.loader import PluginLoader
from plugins.manager import PluginManager

__all__ = ["Plugin", "PluginLoader", "PluginManager"]
