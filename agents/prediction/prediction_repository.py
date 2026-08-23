"""
Prediction Repository Module.

Provides low-level access to the existing predictive engine (engine.model.RiskPredictor)
and recent telemetry metrics needed for feature extraction. Thread-safe persistence and model wrapper.
"""

import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional
import pandas as pd

from agents.core.exceptions import ExecutionError
from agents.core.logger import get_agent_logger
from config.config_manager import ConfigManager
from config.settings import DB_PATH, DEVICE_REGISTRY
from engine.model import RiskPredictor

logger = get_agent_logger("PredictionRepository")


class PredictionRepository:
    """
    Thread-safe repository interfacing directly with the existing predictive engine (RiskPredictor).
    """

    def __init__(
        self,
        predictor: Optional[RiskPredictor] = None,
        db_path: Optional[str] = None,
    ) -> None:
        """
        Initialize PredictionRepository.

        Args:
            predictor: Optional pre-constructed RiskPredictor instance.
            db_path: Optional SQLite database path. Defaults to ConfigManager DB_PATH.
        """
        self._config_manager = ConfigManager.get_instance()
        self._db_path = db_path or self._config_manager.get("DB_PATH", DB_PATH)
        self._predictor = predictor or RiskPredictor()
        self._lock = threading.RLock()

    @property
    def predictor(self) -> RiskPredictor:
        """RiskPredictor model engine instance."""
        return self._predictor

    def fetch_recent_telemetry_df(self, interface: str, window_size: int = 30) -> pd.DataFrame:
        """
        Fetch recent telemetry samples from SQLite database as a Pandas DataFrame.

        Args:
            interface: Name of the interface to query.
            window_size: Number of recent samples (default 30).

        Returns:
            Chronologically ordered DataFrame (oldest to newest).
        """
        current_db_path = self._config_manager.get("DB_PATH", self._db_path)
        if not os.path.exists(current_db_path):
            logger.debug(f"Database path '{current_db_path}' does not exist.")
            return pd.DataFrame()

        query = """
            SELECT timestamp, utilization, latency, jitter, drops, routing_flaps
            FROM metrics
            WHERE interface = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """
        try:
            with self._lock:
                conn = sqlite3.connect(current_db_path, timeout=10.0)
                try:
                    df = pd.read_sql_query(query, conn, params=(interface, max(1, window_size)))
                finally:
                    conn.close()

            if df.empty:
                return pd.DataFrame()

            # Reverse to chronological order (oldest -> newest) for rolling feature calculations
            return df.iloc[::-1].reset_index(drop=True)

        except Exception as e:
            logger.error(f"Error fetching recent telemetry DataFrame for '{interface}': {e}", exc_info=True)
            raise ExecutionError(f"Failed to fetch telemetry DataFrame for interface '{interface}': {e}") from e

    def predict_from_df(self, interface: str, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Pass a recent telemetry DataFrame directly to the prediction engine.

        Args:
            interface: Target interface name.
            df: Chronologically ordered DataFrame containing telemetry metrics.

        Returns:
            Raw prediction output dict from RiskPredictor.
        """
        if df.empty or len(df) == 0:
            return {
                "interface": interface,
                "risk_score": 0.0,
                "time_to_impact": -1.0,
                "contributing_signals": [],
            }

        try:
            with self._lock:
                raw_pred = self._predictor.predict(df)

            raw_pred["interface"] = interface
            return raw_pred

        except Exception as e:
            logger.error(f"Prediction engine error for interface '{interface}': {e}", exc_info=True)
            raise ExecutionError(f"Prediction engine error for interface '{interface}': {e}") from e

    def predict_for_interface(self, interface: str) -> Dict[str, Any]:
        """
        Fetch recent telemetry window for an interface and execute prediction engine.

        Args:
            interface: Name of network interface.

        Returns:
            Raw prediction output dictionary.
        """
        df = self.fetch_recent_telemetry_df(interface, window_size=30)
        return self.predict_from_df(interface, df)

    def predict_fleet(self, interfaces: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Execute prediction engine across all interfaces in the fleet.

        Args:
            interfaces: Optional list of interface names. Defaults to DEVICE_REGISTRY devices.

        Returns:
            Dict mapping interface name to raw prediction result dictionary.
        """
        if not interfaces:
            devices = self._config_manager.get("DEVICE_REGISTRY", DEVICE_REGISTRY)
            interfaces = [d["name"] for d in devices]

        results: Dict[str, Dict[str, Any]] = {}
        for iface in interfaces:
            results[iface] = self.predict_for_interface(iface)

        return results
