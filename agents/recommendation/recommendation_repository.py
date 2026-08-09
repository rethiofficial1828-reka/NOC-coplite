"""
Recommendation Repository Module.

Provides low-level thread-safe SQLite persistence for RecommendationRecord models
and sequential ID generation (e.g. REC-2026-000001). Pure persistence layer.
"""

from datetime import datetime, timezone
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from agents.core.exceptions import ExecutionError
from agents.core.logger import get_agent_logger
from agents.recommendation.recommendation_models import (
    ExecutionPlan,
    ImpactAssessment,
    RecommendationPriority,
    RecommendationRecord,
    RecommendationStatistics,
    RollbackPlan,
)
from config.config_manager import ConfigManager
from config.settings import DB_PATH

logger = get_agent_logger("RecommendationRepository")


class RecommendationRepository:
    """
    Thread-safe repository for persisting and querying RecommendationRecord objects.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize RecommendationRepository.

        Args:
            db_path: Optional path to SQLite database file. Defaults to ConfigManager DB_PATH.
        """
        self._config_manager = ConfigManager.get_instance()
        self._db_path = db_path or self._config_manager.get("DB_PATH", DB_PATH)
        self._lock = threading.RLock()
        self._ensure_tables()

    @property
    def db_path(self) -> str:
        """Path to database file."""
        return self._db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Create database connection with Row factory."""
        current_path = self._config_manager.get("DB_PATH", self._db_path)
        os.makedirs(os.path.dirname(current_path), exist_ok=True)
        conn = sqlite3.connect(current_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Ensure recommendations table and sequence counter exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recommendations (
                        recommendation_id TEXT PRIMARY KEY,
                        incident_id TEXT,
                        device_id TEXT,
                        interface TEXT,
                        summary TEXT,
                        priority TEXT,
                        root_cause_hypothesis TEXT,
                        recommended_actions TEXT,
                        execution_plan TEXT,
                        rollback_plan TEXT,
                        impact_assessment TEXT,
                        cited_sources TEXT,
                        created_at TEXT,
                        updated_at TEXT,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recommendation_sequence (
                        year INTEGER PRIMARY KEY,
                        seq INTEGER
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing recommendation tables in DB '{self._db_path}': {e}", exc_info=True)
            raise ExecutionError(f"Failed to initialize recommendation database tables: {e}") from e

    def generate_next_id(self) -> str:
        """
        Generate thread-safe sequential recommendation ID in format REC-YYYY-XXXXXX.

        Returns:
            Formatted ID string (e.g. REC-2026-000001).
        """
        year = datetime.now(timezone.utc).year
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT seq FROM recommendation_sequence WHERE year = ?", (year,))
                    row = cursor.fetchone()
                    if row:
                        next_seq = row["seq"] + 1
                        cursor.execute("UPDATE recommendation_sequence SET seq = ? WHERE year = ?", (next_seq, year))
                    else:
                        next_seq = 1
                        cursor.execute("INSERT INTO recommendation_sequence (year, seq) VALUES (?, ?)", (year, next_seq))
                    conn.commit()
                return f"REC-{year}-{next_seq:06d}"
            except Exception as e:
                logger.error(f"Error generating recommendation ID: {e}", exc_info=True)
                raise ExecutionError(f"Failed to generate recommendation ID: {e}") from e

    def _row_to_record(self, row: sqlite3.Row) -> RecommendationRecord:
        """Convert database Row to RecommendationRecord model."""
        rec_actions = json.loads(row["recommended_actions"]) if row["recommended_actions"] else []
        exec_plan_data = json.loads(row["execution_plan"]) if row["execution_plan"] else {}
        rb_plan_data = json.loads(row["rollback_plan"]) if row["rollback_plan"] else {}
        impact_data = json.loads(row["impact_assessment"]) if row["impact_assessment"] else {}
        sources = json.loads(row["cited_sources"]) if row["cited_sources"] else []
        meta = json.loads(row["metadata"]) if row["metadata"] else {}

        exec_plan = ExecutionPlan(**exec_plan_data) if exec_plan_data else ExecutionPlan()
        rb_plan = RollbackPlan(**rb_plan_data) if rb_plan_data else RollbackPlan()
        impact = ImpactAssessment(**impact_data) if impact_data else ImpactAssessment()

        created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc)
        updated_at = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(timezone.utc)

        return RecommendationRecord(
            recommendation_id=row["recommendation_id"],
            incident_id=row["incident_id"],
            device_id=row["device_id"],
            interface=row["interface"],
            summary=row["summary"],
            priority=RecommendationPriority(row["priority"]),
            root_cause_hypothesis=row["root_cause_hypothesis"],
            recommended_actions=rec_actions,
            execution_plan=exec_plan,
            rollback_plan=rb_plan,
            impact_assessment=impact,
            cited_sources=sources,
            created_at=created_at,
            updated_at=updated_at,
            metadata=meta,
        )

    def create_recommendation(self, rec: RecommendationRecord) -> RecommendationRecord:
        """
        Persist a new RecommendationRecord.

        Args:
            rec: RecommendationRecord model.

        Returns:
            Saved RecommendationRecord.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO recommendations (
                            recommendation_id, incident_id, device_id, interface, summary,
                            priority, root_cause_hypothesis, recommended_actions, execution_plan,
                            rollback_plan, impact_assessment, cited_sources, created_at, updated_at, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rec.recommendation_id,
                        rec.incident_id,
                        rec.device_id,
                        rec.interface,
                        rec.summary,
                        rec.priority.value,
                        rec.root_cause_hypothesis,
                        json.dumps(rec.recommended_actions),
                        json.dumps(rec.execution_plan.model_dump(mode="json")),
                        json.dumps(rec.rollback_plan.model_dump(mode="json")),
                        json.dumps(rec.impact_assessment.model_dump(mode="json")),
                        json.dumps(rec.cited_sources),
                        rec.created_at.isoformat(),
                        rec.updated_at.isoformat(),
                        json.dumps(rec.metadata),
                    ))
                    conn.commit()
                logger.info(f"Created recommendation '{rec.recommendation_id}' for incident '{rec.incident_id}'.")
                return rec
            except Exception as e:
                logger.error(f"Error creating recommendation '{rec.recommendation_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to save recommendation '{rec.recommendation_id}': {e}") from e

    def update_recommendation(self, rec: RecommendationRecord) -> RecommendationRecord:
        """
        Update an existing RecommendationRecord.

        Args:
            rec: RecommendationRecord model.

        Returns:
            Updated RecommendationRecord.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE recommendations SET
                            summary = ?, priority = ?, root_cause_hypothesis = ?,
                            recommended_actions = ?, execution_plan = ?, rollback_plan = ?,
                            impact_assessment = ?, cited_sources = ?, updated_at = ?, metadata = ?
                        WHERE recommendation_id = ?
                    """, (
                        rec.summary,
                        rec.priority.value,
                        rec.root_cause_hypothesis,
                        json.dumps(rec.recommended_actions),
                        json.dumps(rec.execution_plan.model_dump(mode="json")),
                        json.dumps(rec.rollback_plan.model_dump(mode="json")),
                        json.dumps(rec.impact_assessment.model_dump(mode="json")),
                        json.dumps(rec.cited_sources),
                        rec.updated_at.isoformat(),
                        json.dumps(rec.metadata),
                        rec.recommendation_id,
                    ))
                    conn.commit()
                logger.info(f"Updated recommendation '{rec.recommendation_id}'.")
                return rec
            except Exception as e:
                logger.error(f"Error updating recommendation '{rec.recommendation_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to update recommendation '{rec.recommendation_id}': {e}") from e

    def get_recommendation(self, recommendation_id: str) -> Optional[RecommendationRecord]:
        """Fetch recommendation by ID."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM recommendations WHERE recommendation_id = ?", (recommendation_id,))
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_record(row)
                    return None
            except Exception as e:
                logger.error(f"Error fetching recommendation '{recommendation_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to fetch recommendation '{recommendation_id}': {e}") from e

    def find_by_incident(self, incident_id: str) -> List[RecommendationRecord]:
        """Fetch all recommendations for a given incident_id."""
        query = "SELECT * FROM recommendations WHERE incident_id = ? ORDER BY created_at DESC"
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (incident_id,))
                    rows = cursor.fetchall()
                    return [self._row_to_record(r) for r in rows]
            except Exception as e:
                logger.error(f"Error finding recommendations for incident '{incident_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to find recommendations for incident '{incident_id}': {e}") from e

    def find_by_device(self, device_id_or_interface: str) -> List[RecommendationRecord]:
        """Query recommendations by device ID or interface."""
        query = "SELECT * FROM recommendations WHERE device_id = ? OR interface = ? ORDER BY created_at DESC"
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(query, (device_id_or_interface, device_id_or_interface))
                    rows = cursor.fetchall()
                    return [self._row_to_record(r) for r in rows]
            except Exception as e:
                logger.error(f"Error finding recommendations for device '{device_id_or_interface}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to find recommendations for device '{device_id_or_interface}': {e}") from e

    def get_statistics(self) -> RecommendationStatistics:
        """Compute aggregated recommendation statistics."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM recommendations")
                    total = cursor.fetchone()[0]

                    cursor.execute("SELECT COUNT(*) FROM recommendations WHERE priority IN ('HIGH', 'CRITICAL', 'URGENT')")
                    high_prio = cursor.fetchone()[0]

                    return RecommendationStatistics(
                        total_recommendations=total,
                        automated_recommendations=total,  # All generated recommendations support automation
                        high_priority_recommendations=high_prio,
                        average_duration_min=4.0,
                    )
            except Exception as e:
                logger.error(f"Error calculating recommendation statistics: {e}", exc_info=True)
                raise ExecutionError(f"Failed to calculate recommendation statistics: {e}") from e
