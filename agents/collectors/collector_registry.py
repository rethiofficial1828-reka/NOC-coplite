"""
Thread-Safe Collector Registry.

Manages dynamic runtime registration, discovery, lookup, and lifecycle
management of pluggable telemetry collectors.
"""

import threading
from typing import Dict, List, Optional

from agents.core.exceptions import RegistrationError
from agents.core.logger import get_agent_logger
from agents.collectors.collector_base import CollectorBase

logger = get_agent_logger("CollectorRegistry")


class CollectorRegistry:
    """
    Thread-safe Registry for Telemetry Collectors.
    """

    _global_instance: Optional["CollectorRegistry"] = None
    _global_lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize empty CollectorRegistry."""
        self._collectors: Dict[str, CollectorBase] = {}
        self._id_index: Dict[str, str] = {}  # maps collector_id -> name
        self._lock = threading.RLock()

    @classmethod
    def get_global(cls) -> "CollectorRegistry":
        """Get or create the global singleton CollectorRegistry instance."""
        if cls._global_instance is None:
            with cls._global_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    def register(self, collector: CollectorBase, allow_override: bool = False) -> None:
        """
        Register a collector instance.

        Args:
            collector: CollectorBase instance.
            allow_override: If True, overwrite existing collector with same name.
        """
        if not isinstance(collector, CollectorBase):
            raise RegistrationError(f"Collector must be an instance of CollectorBase, got '{type(collector)}'.")

        name = collector.name
        cid = collector.collector_id

        with self._lock:
            if name in self._collectors and not allow_override:
                raise RegistrationError(
                    f"Collector with name '{name}' is already registered. Set allow_override=True to replace."
                )

            self._collectors[name] = collector
            self._id_index[cid] = name
            logger.info(f"Registered collector '{name}' [source_type={collector.source_type}, id={cid}]")

    def unregister(self, name_or_id: str) -> Optional[CollectorBase]:
        """
        Unregister a collector by name or instance ID.

        Args:
            name_or_id: Collector name or ID string.

        Returns:
            Unregistered CollectorBase instance if found, None otherwise.
        """
        with self._lock:
            target_name = name_or_id
            if name_or_id in self._id_index:
                target_name = self._id_index[name_or_id]

            collector = self._collectors.pop(target_name, None)
            if collector:
                self._id_index.pop(collector.collector_id, None)
                logger.info(f"Unregistered collector '{target_name}'")
                return collector
            return None

    def get(self, name_or_id: str) -> Optional[CollectorBase]:
        """
        Get registered collector by name or ID.

        Args:
            name_or_id: Collector name or ID.

        Returns:
            CollectorBase instance or None if not found.
        """
        with self._lock:
            if name_or_id in self._collectors:
                return self._collectors[name_or_id]
            if name_or_id in self._id_index:
                name = self._id_index[name_or_id]
                return self._collectors.get(name)
            return None

    def exists(self, name_or_id: str) -> bool:
        """
        Check if a collector exists in the registry.

        Args:
            name_or_id: Collector name or ID.

        Returns:
            True if exists, False otherwise.
        """
        with self._lock:
            return name_or_id in self._collectors or name_or_id in self._id_index

    def list_all(self) -> List[CollectorBase]:
        """
        List all registered collectors.

        Returns:
            List of CollectorBase instances.
        """
        with self._lock:
            return list(self._collectors.values())

    def get_by_source_type(self, source_type: str) -> List[CollectorBase]:
        """
        Get all registered collectors matching a specific source type.

        Args:
            source_type: Classification string (e.g. 'snmp', 'syslog').

        Returns:
            List of matching CollectorBase instances.
        """
        target = source_type.strip().lower()
        with self._lock:
            return [c for c in self._collectors.values() if c.source_type.strip().lower() == target]

    def clear(self) -> None:
        """Unregister all collectors."""
        with self._lock:
            self._collectors.clear()
            self._id_index.clear()
            logger.debug("CollectorRegistry cleared.")
