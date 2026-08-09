"""
Telemetry Repository Module.

Provides thread-safe, low-level SQLite persistence access for querying live and historical
device metrics from the telemetry database. Pure persistence layer — no business logic.
"""

import os
import sqlite3

from typing import Any, Dict, List, Optional

from agents.core.exceptions import ExecutionError
from agents.core.logger import get_agent_logger
from config.config_manager import ConfigManager
from config.settings import DB_PATH

logger = get_agent_logger("TelemetryRepository")


class TelemetryRepository:
    """
    Thread-safe repository for reading network metrics from SQLite telemetry database.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize TelemetryRepository.

        Args:
            db_path: Optional custom path to SQLite database file. Defaults to ConfigManager DB_PATH.
        """
        self._db_path = db_path or ConfigManager.get_instance().get("DB_PATH", DB_PATH)
        self._ensure_db_initialized()

    @property
    def db_path(self) -> str:
        """Path to SQLite database."""
        return self._db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a new SQLite database connection."""
        try:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database at '{self._db_path}': {e}", exc_info=True)
            raise ExecutionError(f"Database connection error at '{self._db_path}': {e}") from e

    def _ensure_db_initialized(self) -> None:
        """Ensure metrics table schema exists."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS metrics (
                        timestamp REAL,
                        interface TEXT,
                        utilization REAL,
                        latency REAL,
                        jitter REAL,
                        drops REAL,
                        routing_flaps INTEGER
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize telemetry database table: {e}", exc_info=True)
            raise ExecutionError(f"Failed to initialize telemetry table: {e}") from e

    def get_latest_telemetry(self, interface: str) -> Optional[Dict[str, Any]]:
        """
        Query the single most recent telemetry record for a specific interface.

        Args:
            interface: Name of the interface/device (e.g. 'Branch3-Uplink').

        Returns:
            Dict representing the row, or None if no record exists.
        """
        query = """
            SELECT timestamp, interface, utilization, latency, jitter, drops, routing_flaps
            FROM metrics
            WHERE interface = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (interface,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except sqlite3.Error as e:
            logger.error(f"Error querying latest telemetry for interface '{interface}': {e}", exc_info=True)
            raise ExecutionError(f"Database query error for interface '{interface}': {e}") from e

    def get_all_latest_telemetry(self) -> List[Dict[str, Any]]:
        """
        Query the most recent telemetry sample for each interface in the database.

        Returns:
            List of dicts representing the latest metrics record per interface.
        """
        query = """
            SELECT m.timestamp, m.interface, m.utilization, m.latency, m.jitter, m.drops, m.routing_flaps
            FROM metrics m
            INNER JOIN (
                SELECT interface, MAX(timestamp) AS max_ts
                FROM metrics
                GROUP BY interface
            ) latest ON m.interface = latest.interface AND m.timestamp = latest.max_ts
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error(f"Error querying all latest telemetry records: {e}", exc_info=True)
            raise ExecutionError(f"Database query error fetching all latest telemetry: {e}") from e

    def get_historical_telemetry(self, interface: str, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Query historical telemetry samples for an interface.

        Args:
            interface: Name of interface.
            limit: Maximum number of rows to return (default 30).

        Returns:
            List of dicts ordered by timestamp ASC.
        """
        query = """
            SELECT timestamp, interface, utilization, latency, jitter, drops, routing_flaps
            FROM (
                SELECT timestamp, interface, utilization, latency, jitter, drops, routing_flaps
                FROM metrics
                WHERE interface = ?
                ORDER BY timestamp DESC
                LIMIT ?
            )
            ORDER BY timestamp ASC
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (interface, max(1, limit)))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error(f"Error querying historical telemetry for '{interface}': {e}", exc_info=True)
            raise ExecutionError(f"Database query error fetching historical telemetry for '{interface}': {e}") from e

    def get_telemetry_by_device(self, interface_or_device: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Convenience method for querying telemetry by device/interface name."""
        return self.get_historical_telemetry(interface_or_device, limit=limit)

    def get_telemetry_by_timerange(
        self,
        interface: str,
        start_time: float,
        end_time: float,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query telemetry samples within a specific epoch timestamp range with pagination.

        Args:
            interface: Name of interface.
            start_time: Start timestamp inclusive (epoch seconds).
            end_time: End timestamp inclusive (epoch seconds).
            limit: Pagination limit.
            offset: Pagination offset.

        Returns:
            List of dicts ordered by timestamp ASC.
        """
        query = """
            SELECT timestamp, interface, utilization, latency, jitter, drops, routing_flaps
            FROM metrics
            WHERE interface = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
            LIMIT ? OFFSET ?
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (interface, start_time, end_time, max(1, limit), max(0, offset)))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except sqlite3.Error as e:
            logger.error(
                f"Error querying telemetry range for '{interface}' ({start_time}-{end_time}): {e}",
                exc_info=True,
            )
            raise ExecutionError(
                f"Database query error fetching timerange telemetry for '{interface}': {e}"
            ) from e
