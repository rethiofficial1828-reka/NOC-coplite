"""
Comprehensive Unit Test Suite for Production PredictionAgent, PredictionService,
PredictionRepository, and PredictionValidator.
"""

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.core.container import ServiceContainer
from agents.core.exceptions import ValidationError
from agents.events import Event, EventBus
from agents.prediction import (
    PredictionAgent,
    PredictionRepository,
    PredictionService,
    PredictionValidator,
    register_prediction_agent,
)
from agents.registry import AgentRegistry
from agents.schemas import ExecutionContext, PredictionResult, TelemetryPacket
from agents.telemetry import TelemetryAgent
from config.config_manager import ConfigManager


class TestPredictionAgentFramework(unittest.TestCase):

    def setUp(self):
        # Create temporary database file
        self.temp_db = tempfile.NamedTemporaryFile("w", delete=False, suffix=".db")
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        # Seed telemetry metrics into temporary DB
        self._seed_database()

        # Configure repositories & services
        ConfigManager.get_instance().reset_overrides()
        ConfigManager.get_instance().set_override("DB_PATH", self.temp_db_path)

        self.repo = PredictionRepository(db_path=self.temp_db_path)
        self.service = PredictionService(repository=self.repo)
        self.event_bus = EventBus()
        self.container = ServiceContainer()
        self.registry = AgentRegistry(container=self.container)

        # Clear global singletons
        EventBus.get_global().clear()
        AgentRegistry.get_global().clear()

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def _seed_database(self):
        """Seed 30 telemetry samples to test rolling feature extraction."""
        conn = sqlite3.connect(self.temp_db_path)
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

        now = time.time()
        records = []
        for i in range(30):
            t = now - (30 - i) * 2
            u = 50.0 + (i * 1.2)  # Ramp up utilization
            l = 20.0 + (i * 3.0)  # Ramp up latency
            records.append((t, "Branch3-Uplink", u, l, 3.0, 0.0, 0))
            records.append((t, "Campus Core", 45.0, 5.0, 1.0, 0.0, 0))

        cursor.executemany("""
            INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        conn.close()

    def test_01_prediction_repository(self):
        """Test PredictionRepository fetching telemetry DataFrame and calling ML engine."""
        df = self.repo.fetch_recent_telemetry_df("Branch3-Uplink", window_size=30)
        self.assertEqual(len(df), 30)
        self.assertIn("utilization", df.columns)

        raw_pred = self.repo.predict_for_interface("Branch3-Uplink")
        self.assertIn("risk_score", raw_pred)
        self.assertIn("time_to_impact", raw_pred)
        self.assertIn("contributing_signals", raw_pred)
        self.assertTrue(0.0 <= raw_pred["risk_score"] <= 1.0)

    def test_02_prediction_validator(self):
        """Test PredictionValidator bounds checks and exception handling."""
        valid_raw = {
            "interface": "Branch3-Uplink",
            "risk_score": 0.75,
            "time_to_impact": 10.5,
            "contributing_signals": ["utilization elevated at 85.0%"],
        }
        validated = PredictionValidator.validate_raw_prediction(valid_raw)
        self.assertEqual(validated["risk_score"], 0.75)

        invalid_cases = [
            {**valid_raw, "risk_score": 1.5},    # Risk > 1.0
            {**valid_raw, "risk_score": -0.1},   # Risk < 0.0
            {**valid_raw, "time_to_impact": -5.0}, # TTI < -1.0
            {**valid_raw, "interface": ""},       # Empty interface
            {**valid_raw, "contributing_signals": "invalid_type"}, # Not a list
        ]

        for case in invalid_cases:
            with self.assertRaises(ValidationError):
                PredictionValidator.validate_raw_prediction(case)

    def test_03_prediction_service(self):
        """Test PredictionService conversion into PredictionResult objects."""
        res = self.service.predict_for_interface("Branch3-Uplink")
        self.assertIsInstance(res, PredictionResult)
        self.assertEqual(res.interface, "Branch3-Uplink")
        self.assertTrue(0.0 <= res.risk_score <= 1.0)

        # Fleet prediction
        fleet = self.service.predict_fleet(interfaces=["Branch3-Uplink", "Campus Core"])
        self.assertEqual(len(fleet), 2)

    def test_04_prediction_agent_execution_and_events(self):
        """Test PredictionAgent direct execution, event publication, and ExecutionContext."""
        generated_events: List[Event] = []

        def event_handler(evt: Event):
            generated_events.append(evt)

        self.event_bus.subscribe("prediction.generated", event_handler)

        agent = PredictionAgent(service=self.service, event_bus=self.event_bus)
        self.assertEqual(agent.name, "PredictionAgent")

        ctx = ExecutionContext()
        results = agent.execute({"interface": "Branch3-Uplink"}, context=ctx)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(generated_events), 1)

        # Verify event content
        evt = generated_events[0]
        self.assertEqual(evt.event_type, "prediction.generated")
        self.assertEqual(evt.source, "PredictionAgent")
        self.assertIn("risk_score", evt.metadata)

        # Verify context
        self.assertIn("PredictionAgent", ctx.results)
        self.assertIn("Branch3-Uplink", ctx.shared_state["latest_predictions"])

    def test_05_telemetry_to_prediction_event_driven_pipeline(self):
        """Test reactive event pipeline: TelemetryAgent publishes telemetry.updated -> PredictionAgent executes automatically."""
        prediction_events: List[Event] = []

        def pred_handler(evt: Event):
            prediction_events.append(evt)

        # Use global event bus
        bus = EventBus.get_global()
        bus.subscribe("prediction.generated", pred_handler)

        # Initialize TelemetryAgent and PredictionAgent
        telemetry_agent = TelemetryAgent(event_bus=bus)
        prediction_agent = register_prediction_agent(registry=self.registry)
        prediction_agent._event_bus = bus
        prediction_agent._setup_event_subscription()

        # Execute TelemetryAgent for Branch3-Uplink
        telemetry_agent.execute({"device_id": "Branch3-Uplink", "mode": "latest"})

        # Assert PredictionAgent ran automatically via event subscription
        self.assertTrue(len(prediction_events) >= 1)
        self.assertEqual(prediction_events[0].event_type, "prediction.generated")
        self.assertEqual(prediction_events[0].source, "PredictionAgent")

    def test_06_thread_safe_concurrent_predictions(self):
        """Test concurrent multi-threaded execution of PredictionAgent."""
        agent = PredictionAgent(service=self.service, event_bus=self.event_bus)

        def worker_task(i: int):
            ctx = ExecutionContext()
            res = agent.execute({"interface": "Branch3-Uplink"}, context=ctx)
            return len(res)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(10)]
            results = [f.result() for f in futures]

        self.assertEqual(results, [1] * 10)
        self.assertEqual(agent.metrics.execution_count, 10)
        self.assertEqual(agent.metrics.success_count, 10)


if __name__ == "__main__":
    unittest.main()
