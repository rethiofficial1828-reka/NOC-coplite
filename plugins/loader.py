"""
Plugin Loader for Dynamic Module Discovery and Importing.
"""

import importlib
import importlib.util
import os
import sys
from typing import List, Type

from agents.core.logger import get_agent_logger
from plugins.base import Plugin

logger = get_agent_logger("PluginLoader")


class PluginLoader:
    """
    Dynamic plugin loader for discovering and importing plugin classes.
    """

    @staticmethod
    def load_plugin_from_file(file_path: str) -> List[Type[Plugin]]:
        """
        Dynamically import a Python file and discover subclasses of Plugin.

        Args:
            file_path: Path to Python source file.

        Returns:
            List of Plugin class types found in the file.
        """
        if not os.path.exists(file_path) or not file_path.endswith(".py"):
            logger.warning(f"Plugin file path invalid or not a python file: {file_path}")
            return []

        module_name = f"noc_plugin_{os.path.splitext(os.path.basename(file_path))[0]}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            logger.warning(f"Could not create import spec for plugin file: {file_path}")
            return []

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Failed to execute plugin module '{file_path}': {e}", exc_info=True)
            return []

        discovered: List[Type[Plugin]] = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Plugin)
                and attr is not Plugin
            ):
                discovered.append(attr)

        logger.info(f"Discovered {len(discovered)} plugin(s) in '{file_path}'")
        return discovered

    @classmethod
    def discover_plugins_in_directory(cls, directory_path: str) -> List[Type[Plugin]]:
        """
        Discover all Plugin subclasses in python files within a directory.

        Args:
            directory_path: Directory path to scan.

        Returns:
            List of discovered Plugin class types.
        """
        if not os.path.isdir(directory_path):
            logger.warning(f"Plugin directory does not exist: {directory_path}")
            return []

        discovered: List[Type[Plugin]] = []
        for root, _, files in os.walk(directory_path):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    file_path = os.path.join(root, file)
                    discovered.extend(cls.load_plugin_from_file(file_path))

        return discovered
