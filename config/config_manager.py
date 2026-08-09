"""
Configuration Manager Module.

Provides a unified, thread-safe configuration management wrapper around settings.py
supporting JSON, YAML, Environment Variables, CLI Overrides, and Runtime Mutability.
"""

import json
import os
import threading
from typing import Any, Dict, Optional, Union

import config.settings as settings


class ConfigManager:
    """
    Centralized Configuration Manager for NOC Copilot.

    Wraps config.settings and provides runtime override capabilities,
    dict loading, JSON/YAML file loading, and environment variable parsing.
    """

    _instance: Optional["ConfigManager"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._overrides: Dict[str, Any] = {}
        self._config_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """Get or create singleton instance of ConfigManager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a configuration setting by key.

        Lookup precedence:
        1. Runtime overrides
        2. Environment variables
        3. Module attributes in config.settings
        4. Provided default value
        """
        with self._config_lock:
            if key in self._overrides:
                return self._overrides[key]

            env_key = f"NOC_COPILOT_{key.upper()}"
            if env_key in os.environ:
                val = os.environ[env_key]
                return self._cast_env_value(val)

            if hasattr(settings, key):
                return getattr(settings, key)

            return default

    def set_override(self, key: str, value: Any) -> None:
        """Set a runtime configuration override."""
        with self._config_lock:
            self._overrides[key] = value

    def remove_override(self, key: str) -> None:
        """Remove a specific runtime configuration override."""
        with self._config_lock:
            self._overrides.pop(key, None)

    def reset_overrides(self) -> None:
        """Clear all runtime configuration overrides."""
        with self._config_lock:
            self._overrides.clear()

    def load_from_dict(self, data: Dict[str, Any], overwrite: bool = True) -> None:
        """Load configuration key-values from a dictionary into overrides."""
        with self._config_lock:
            for k, v in data.items():
                if overwrite or k not in self._overrides:
                    self._overrides[k] = v

    def load_from_json(self, file_path: str) -> None:
        """Load configuration from a JSON file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            self.load_from_dict(data)

    def load_from_yaml(self, file_path: str) -> None:
        """Load configuration from a YAML file if PyYAML is available."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError(
                "PyYAML library is required to load YAML configuration files."
            )

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, dict):
            self.load_from_dict(data)

    def _cast_env_value(self, value: str) -> Union[int, float, bool, str]:
        """Convert string environment variables to appropriate python types."""
        val_lower = value.strip().lower()
        if val_lower == "true":
            return True
        if val_lower == "false":
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value


def get_config_manager() -> ConfigManager:
    """Convenience accessor for global ConfigManager singleton."""
    return ConfigManager.get_instance()
