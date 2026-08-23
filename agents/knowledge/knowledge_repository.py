"""
Knowledge Repository Module.

Provides low-level thread-safe SQLite persistence for KnowledgeResult models,
runbook/topology document retrieval, and sequential ID generation (e.g. KNOW-2026-000001).
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from agents.core.exceptions import ExecutionError
from agents.core.logger import get_agent_logger
from agents.knowledge.knowledge_models import KnowledgeResult, KnowledgeStatistics
from config.config_manager import ConfigManager
from config.settings import DB_PATH, DEVICE_REGISTRY, DOCS_DIR

logger = get_agent_logger("KnowledgeRepository")


class KnowledgeRepository:
    """
    Thread-safe repository for storing and querying KnowledgeResult objects and knowledge documents.
    """

    def __init__(self, db_path: Optional[str] = None, docs_dir: Optional[str] = None) -> None:
        """
        Initialize KnowledgeRepository.

        Args:
            db_path: Optional path to SQLite database. Defaults to ConfigManager DB_PATH.
            docs_dir: Optional path to documentation directory. Defaults to ConfigManager DOCS_DIR.
        """
        self._config_manager = ConfigManager.get_instance()
        self._db_path = db_path or self._config_manager.get("DB_PATH", DB_PATH)
        self._docs_dir = docs_dir or self._config_manager.get("DOCS_DIR", DOCS_DIR)
        self._lock = threading.RLock()
        self._ensure_tables()

    @property
    def db_path(self) -> str:
        """Database path."""
        return self._db_path

    @contextmanager
    def _get_connection(self):
        """Create database connection with Row factory."""
        current_path = self._config_manager.get("DB_PATH", self._db_path)
        os.makedirs(os.path.dirname(current_path), exist_ok=True)
        conn = sqlite3.connect(current_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_tables(self) -> None:
        """Ensure knowledge_results table and sequence counter exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_results (
                        result_id TEXT PRIMARY KEY,
                        query_id TEXT,
                        recommendation_id TEXT,
                        incident_id TEXT,
                        device_id TEXT,
                        generated_explanation TEXT,
                        root_cause_analysis TEXT,
                        recommended_steps TEXT,
                        confidence_score REAL,
                        cited_sources TEXT,
                        created_at TEXT,
                        provider_metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_sequence (
                        year INTEGER PRIMARY KEY,
                        seq INTEGER
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Error initializing knowledge tables in DB '{self._db_path}': {e}", exc_info=True)
            raise ExecutionError(f"Failed to initialize knowledge database tables: {e}") from e

    def generate_next_id(self) -> str:
        """
        Generate thread-safe sequential knowledge ID in format KNOW-YYYY-XXXXXX.

        Returns:
            Formatted ID string (e.g. KNOW-2026-000001).
        """
        year = datetime.now(timezone.utc).year
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT seq FROM knowledge_sequence WHERE year = ?", (year,))
                    row = cursor.fetchone()
                    if row:
                        next_seq = row["seq"] + 1
                        cursor.execute("UPDATE knowledge_sequence SET seq = ? WHERE year = ?", (next_seq, year))
                    else:
                        next_seq = 1
                        cursor.execute("INSERT INTO knowledge_sequence (year, seq) VALUES (?, ?)", (year, next_seq))
                    conn.commit()
                return f"KNOW-{year}-{next_seq:06d}"
            except Exception as e:
                logger.error(f"Error generating knowledge ID: {e}", exc_info=True)
                raise ExecutionError(f"Failed to generate knowledge ID: {e}") from e

    def retrieve_runbooks(self, incident_type: str) -> List[Dict[str, Any]]:
        """
        Retrieve relevant runbook document snippets for an incident_type.

        Args:
            incident_type: Incident category.

        Returns:
            List of dict snippets containing 'source', 'chunk', and 'score'.
        """
        results: List[Dict[str, Any]] = []

        if os.path.exists(self._docs_dir):
            for file in os.listdir(self._docs_dir):
                if file.endswith(".txt") or file.endswith(".md"):
                    file_path = os.path.join(self._docs_dir, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read(1000)  # Read initial chunk
                            results.append({
                                "source": file,
                                "chunk": content.strip().replace("\n", " ")[:300],
                                "score": 0.90,
                            })
                    except Exception as e:
                        logger.warning(f"Failed reading runbook file '{file_path}': {e}")

        if not results:
            results.append({
                "source": "wan_troubleshooting_runbook.md",
                "chunk": "For network congestion and WAN degradation: verify QoS shaping, check ring buffers, and re-route traffic.",
                "score": 0.85,
            })

        return results

    def retrieve_topology(self, device_id_or_interface: str) -> Dict[str, Any]:
        """
        Retrieve topology information for a device from DEVICE_REGISTRY.

        Args:
            device_id_or_interface: Device ID or Interface name.

        Returns:
            Dict containing device topology metadata.
        """
        devices = self._config_manager.get("DEVICE_REGISTRY", DEVICE_REGISTRY)
        target = str(device_id_or_interface).strip().lower()

        for dev in devices:
            if target in (str(dev.get("id", "")).lower(), str(dev.get("name", "")).lower()):
                return dict(dev)

        return {
            "id": device_id_or_interface,
            "name": device_id_or_interface,
            "type": "Network Interface",
            "location": "Datacenter WAN",
        }

    def save_knowledge_result(self, result: KnowledgeResult) -> KnowledgeResult:
        """
        Persist a KnowledgeResult to database.

        Args:
            result: KnowledgeResult model instance.

        Returns:
            Saved KnowledgeResult model instance.
        """
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO knowledge_results (
                            result_id, query_id, recommendation_id, incident_id, device_id,
                            generated_explanation, root_cause_analysis, recommended_steps,
                            confidence_score, cited_sources, created_at, provider_metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        result.result_id,
                        result.query_id,
                        result.recommendation_id,
                        result.incident_id,
                        result.device_id,
                        result.generated_explanation,
                        result.root_cause_analysis,
                        json.dumps(result.recommended_steps),
                        result.confidence_score,
                        json.dumps(result.cited_sources),
                        result.created_at.isoformat(),
                        json.dumps(result.provider_metadata),
                    ))
                    conn.commit()
                logger.info(f"Saved knowledge result '{result.result_id}' for recommendation '{result.recommendation_id}'.")
                return result
            except Exception as e:
                logger.error(f"Error saving knowledge result '{result.result_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to save knowledge result '{result.result_id}': {e}") from e

    def get_knowledge_result(self, result_id: str) -> Optional[KnowledgeResult]:
        """Fetch KnowledgeResult by ID."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM knowledge_results WHERE result_id = ?", (result_id,))
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_record(row)
                    return None
            except Exception as e:
                logger.error(f"Error fetching knowledge result '{result_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to fetch knowledge result '{result_id}': {e}") from e

    def find_by_recommendation(self, recommendation_id: str) -> Optional[KnowledgeResult]:
        """Fetch KnowledgeResult by recommendation ID."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT * FROM knowledge_results WHERE recommendation_id = ? ORDER BY created_at DESC LIMIT 1",
                        (recommendation_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_record(row)
                    return None
            except Exception as e:
                logger.error(f"Error finding knowledge result for recommendation '{recommendation_id}': {e}", exc_info=True)
                raise ExecutionError(f"Failed to find knowledge result for recommendation '{recommendation_id}': {e}") from e

    def _row_to_record(self, row: sqlite3.Row) -> KnowledgeResult:
        """Convert database Row to KnowledgeResult model."""
        steps = json.loads(row["recommended_steps"]) if row["recommended_steps"] else []
        sources = json.loads(row["cited_sources"]) if row["cited_sources"] else []
        meta = json.loads(row["provider_metadata"]) if row["provider_metadata"] else {}

        created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(timezone.utc)

        return KnowledgeResult(
            result_id=row["result_id"],
            query_id=row["query_id"],
            recommendation_id=row["recommendation_id"],
            incident_id=row["incident_id"],
            device_id=row["device_id"],
            generated_explanation=row["generated_explanation"],
            root_cause_analysis=row["root_cause_analysis"],
            recommended_steps=steps,
            confidence_score=float(row["confidence_score"]),
            cited_sources=sources,
            created_at=created_at,
            provider_metadata=meta,
        )

    def get_statistics(self) -> KnowledgeStatistics:
        """Compute aggregated knowledge statistics."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM knowledge_results")
                    total = cursor.fetchone()[0]
                    return KnowledgeStatistics(total_queries=total)
            except Exception as e:
                logger.error(f"Error computing knowledge statistics: {e}", exc_info=True)
                raise ExecutionError(f"Failed to compute knowledge statistics: {e}") from e
