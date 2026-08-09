"""
Incident Repository Module.

Provides low-level thread-safe SQLite persistence for incident records, timeline audit events,
and sequential incident ID generation (e.g. INC-2026-000001). Pure persistence layer.
"""

from datetime import datetime, timezone
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from agents.core.exceptions import ExecutionError
from agents.core.logger import get_agent_logger
from agents.incident.incident_models import (
    IncidentAssignment,
    IncidentRecord,
    IncidentSeverity,
    IncidentStatistics,
    IncidentStatus,
    IncidentTimeline,
)
from config.config_manager import ConfigManager
from config.settings import DB_PATH

logger = get_agent_logger("IncidentRepository")


class IncidentRepository:
    """
    Thread-safe repository for persisting and querying incident records and timeline events.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize IncidentRepository.

        Args:
            db_path: Optional path to SQLite database. Defaults to ConfigManager DB_PATH.
        """
        self._config_manager = ConfigManager.get_instance()
        self._db_path = db_path or self._config_manager.get("DB_PATH", DB_PATH)
        self._lock = threading.RLock()
        self._ensure_tables()

    @property
    def db_path(self) -> str:
        """Path to database."""
        return self._db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Create database connection with Row factory."""
        current_path = self._config_manager.get("DB_PATH", self._db_path)
        os.makedirs(os.path.dirname(current_path), exist_ok=True)
        conn = sqlite3.connect(current_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Ensure incidents, timeline, and sequence tables exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS incidents (
                        incident_id TEXT PRIMARY KEY,
                        device_id TEXT,
                        interface TEXT,
                        incident_type TEXT,
                        title TEXT,
                        description TEXT,
                        severity TEXT,
                        status TEXT,
                        risk_score REAL,
                        time_to_impact REAL,
                        contributing_signals TEXT,
                        assignment TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        resolved_at TEXT,
                        closed_at TEXT,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS incident_timeline (
                        event_id TEXT PRIMARY KEY,
                        incident_id TEXT,
                        event_type TEXT,
                        description TEXT,
                        timestamp TEXT,
                        author TEXT,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS incident_sequence (
                        year INTEGER PRIMARY KEY,
                        seq INTEGER
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing incident tables in DB '{self._db_path}': {e}", exc_info=True)
            raise ExecutionError(f"Failed to initialize incident database tables: {e}") from e

    def generate_next_id(self) -> str:
        """
        Generate thread-safe sequential incident ID in format INC-YYYY-XXXXXX.

        Returns:
            Formatted incident ID string (e.g. INC-2026-000001).
        """
        year = datetime.now(timezone.utc).year
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT seq FROM incident_sequence WHERE year = ?", (year,))
                    row = cursor.fetchone()
                    if row:
                        next_seq = row["seq"] + 1
                        cursor.execute("UPDATE incident_sequence SET seq = ? WHERE year = ?", (next_seq, year))
                    else:
                        next_seq = 1
                        cursor.execute("INSERT INTO incident_sequence (year, seq) VALUES (?, ?)", (year, next_seq))
                    conn.commit()
                return f"INC-{year}-{next_seq:06d}"
            except Exception as e:
                logger.error(f"Error generating sequential incident ID: {e}", exc_info=True)
                raise ExecutionError(f"Failed to generate incident ID: {e}") from e

    def _row_to_record(self, row: sqlite3.Row, timeline: Optional[List[IncidentTimeline]] = None) -> IncidentRecord:
        """Convert database Row to IncidentRecord model."""
        signals = json.loads(row["contributing_signals"]) if row["contributing_signals"] else []
        assignment_data = json.loads(row["assignment"]) if row["assignment"] else {}
        meta = json.loads(row["metadata"]) if row["metadata"] else {}

        assignment = IncidentAssignment(**assignment_data) if assignment_data else IncidentAssignment()
        tl = timeline if timeline is not None else self.get_timeline(row["incident_id"])

        created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc)
        updated_at = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(timezone.utc)
        resolved_at = datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None
        closed_at = datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None

        return IncidentRecord(
            incident_id=row["incident_id"],
            device_id=row["device_id"],
            interface=row["interface"],
            incident_type=row["incident_type"],
            title=row["title"],
            description=row["description"],
            severity=IncidentSeverity(row["severity"]),
            status=IncidentStatus(row["status"]),
            risk_score=float(row["risk_score"]),
            time_to_impact=float(row["time_to_impact"]),
            contributing_signals=signals,
            assignment=assignment,
            timeline=tl,
            created_at=created_at,
            updated_at=updated_at,
            resolved_at=resolved_at,
            closed_at=closed_at,
            metadata=meta,
        )

    def create_incident(self, incident: IncidentRecord) -> IncidentRecord:
        """
        Persist a new IncidentRecord and its timeline events.

        Args:
            incident: IncidentRecord model.

        Returns:
            Saved IncidentRecord model.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO incidents (
                            incident_id, device_id, interface, incident_type, title, description,
                            severity, status, risk_score, time_to_impact, contributing_signals,
                            assignment, created_at, updated_at, resolved_at, closed_at, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        incident.incident_id,
                        incident.device_id,
                        incident.interface,
                        incident.incident_type,
                        incident.title,
                        incident.description,
                        incident.severity.value,
                        incident.status.value,
                        incident.risk_score,
                        incident.time_to_impact,
                        json.dumps(incident.contributing_signals),
                        json.dumps(incident.assignment.model_dump(mode="json")),
                        incident.created_at.isoformat(),
                        incident.updated_at.isoformat(),
                        incident.resolved_at.isoformat() if incident.resolved_at else None,
                        incident.closed_at.isoformat() if incident.closed_at else None,
                        json.dumps(incident.metadata),
                    ))

                    # Insert timeline events
                    for event in incident.timeline:
                        cursor.execute("""
                            INSERT OR IGNORE INTO incident_timeline (
                                event_id, incident_id, event_type, description, timestamp, author, metadata
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            event.event_id,
                            event.incident_id,
                            event.event_type,
                            event.description,
                            event.timestamp.isoformat(),
                            event.author,
                            json.dumps(event.metadata),
                        ))

                    conn.commit()
                logger.info(f"Created incident '{incident.incident_id}' for device '{incident.device_id}'.")
                return incident
            except Exception as e:
                logger.error(f"Error creating incident '{incident.incident_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to save incident '{incident.incident_id}': {e}") from e

    def update_incident(self, incident: IncidentRecord) -> IncidentRecord:
        """
        Update an existing IncidentRecord and append new timeline entries.

        Args:
            incident: IncidentRecord model.

        Returns:
            Updated IncidentRecord model.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE incidents SET
                            severity = ?, status = ?, risk_score = ?, time_to_impact = ?,
                            contributing_signals = ?, assignment = ?, updated_at = ?,
                            resolved_at = ?, closed_at = ?, metadata = ?
                        WHERE incident_id = ?
                    """, (
                        incident.severity.value,
                        incident.status.value,
                        incident.risk_score,
                        incident.time_to_impact,
                        json.dumps(incident.contributing_signals),
                        json.dumps(incident.assignment.model_dump(mode="json")),
                        incident.updated_at.isoformat(),
                        incident.resolved_at.isoformat() if incident.resolved_at else None,
                        incident.closed_at.isoformat() if incident.closed_at else None,
                        json.dumps(incident.metadata),
                        incident.incident_id,
                    ))

                    # Insert any missing timeline events
                    for event in incident.timeline:
                        cursor.execute("""
                            INSERT OR IGNORE INTO incident_timeline (
                                event_id, incident_id, event_type, description, timestamp, author, metadata
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            event.event_id,
                            event.incident_id,
                            event.event_type,
                            event.description,
                            event.timestamp.isoformat(),
                            event.author,
                            json.dumps(event.metadata),
                        ))

                    conn.commit()
                logger.info(f"Updated incident '{incident.incident_id}'.")
                return incident
            except Exception as e:
                logger.error(f"Error updating incident '{incident.incident_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to update incident '{incident.incident_id}': {e}") from e

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        """Get IncidentRecord by ID."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM incidents WHERE incident_id = ?", (incident_id,))
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_record(row)
                    return None
            except Exception as e:
                logger.error(f"Error fetching incident '{incident_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to fetch incident '{incident_id}': {e}") from e

    def find_active_incident(
        self, device_id_or_interface: str, incident_type: Optional[str] = None
    ) -> Optional[IncidentRecord]:
        """
        Find an active (non-RESOLVED, non-CLOSED) incident for a device.

        Args:
            device_id_or_interface: Device ID or Interface name.
            incident_type: Optional incident category.

        Returns:
            IncidentRecord if an active incident exists, None otherwise.
        """
        query = """
            SELECT * FROM incidents
            WHERE (device_id = ? OR interface = ?)
            AND status NOT IN ('RESOLVED', 'CLOSED')
        """
        params: List[Any] = [device_id_or_interface, device_id_or_interface]
        if incident_type:
            query += " AND incident_type = ?"
            params.append(incident_type)

        query += " ORDER BY created_at DESC LIMIT 1"

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_record(row)
                    return None
            except Exception as e:
                logger.error(f"Error finding active incident for '{device_id_or_interface}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to find active incident for '{device_id_or_interface}': {e}") from e

    def find_incidents_by_device(self, device_id_or_interface: str) -> List[IncidentRecord]:
        """Query all incidents for a specific device."""
        query = "SELECT * FROM incidents WHERE device_id = ? OR interface = ? ORDER BY created_at DESC"
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (device_id_or_interface, device_id_or_interface))
                    rows = cursor.fetchall()
                    return [self._row_to_record(r) for r in rows]
            except Exception as e:
                logger.error(f"Error querying incidents for device '{device_id_or_interface}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to query incidents for device '{device_id_or_interface}': {e}") from e

    def find_incidents_by_severity(self, severity: IncidentSeverity) -> List[IncidentRecord]:
        """Query all incidents matching a given severity level."""
        query = "SELECT * FROM incidents WHERE severity = ? ORDER BY created_at DESC"
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (severity.value,))
                    rows = cursor.fetchall()
                    return [self._row_to_record(r) for r in rows]
            except Exception as e:
                logger.error(f"Error querying incidents by severity '{severity.value}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to query incidents by severity '{severity.value}': {e}") from e

    def find_incidents_by_status(self, status: IncidentStatus) -> List[IncidentRecord]:
        """Query all incidents matching a given status."""
        query = "SELECT * FROM incidents WHERE status = ? ORDER BY created_at DESC"
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (status.value,))
                    rows = cursor.fetchall()
                    return [self._row_to_record(r) for r in rows]
            except Exception as e:
                logger.error(f"Error querying incidents by status '{status.value}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to query incidents by status '{status.value}': {e}") from e

    def get_timeline(self, incident_id: str) -> List[IncidentTimeline]:
        """Fetch all timeline audit events for an incident."""
        query = "SELECT * FROM incident_timeline WHERE incident_id = ? ORDER BY timestamp ASC"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (incident_id,))
                rows = cursor.fetchall()
                timeline = []
                for r in rows:
                    meta = json.loads(r["metadata"]) if r["metadata"] else {}
                    timeline.append(
                        IncidentTimeline(
                            event_id=r["event_id"],
                            incident_id=r["incident_id"],
                            event_type=r["event_type"],
                            description=r["description"],
                            timestamp=datetime.fromisoformat(r["timestamp"]),
                            author=r["author"],
                            metadata=meta,
                        )
                    )
                return timeline
        except Exception as e:
            logger.error(f"Error querying timeline for incident '{incident_id}': {e}", exc_info=True)
            raise ExecutionError(f"Failed to query timeline for incident '{incident_id}': {e}") from e

    def get_statistics(self) -> IncidentStatistics:
        """Compute aggregated incident statistics."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM incidents")
                    total = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM incidents WHERE status NOT IN ('RESOLVED', 'CLOSED')")
                    open_cnt = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM incidents WHERE status = 'CLOSED'")
                    closed_cnt = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM incidents WHERE severity = 'CRITICAL'")
                    crit_cnt = cursor.fetchone()[0]

                    return IncidentStatistics(
                        total_incidents=total,
                        open_incidents=open_cnt,
                        closed_incidents=closed_cnt,
                        critical_incidents=crit_cnt,
                    )
            except Exception as e:
                logger.error(f"Error fetching incident statistics: {e}", exc_info=True)
                raise ExecutionError(f"Failed to compute incident statistics: {e}") from e
