"""
Comprehensive Unit Test Suite for Production TelemetryAgent, TelemetryService,
TelemetryRepository, and TelemetryValidator.
"""

import os
import sqlite3
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.core.container import ServiceContainer
from agents.core.exceptions import ValidationError
from agents.events import Event, EventBus
from agents.registry import AgentRegistry
from agents.schemas import ExecutionContext, TelemetryPacket
from agents.telemetry import (
    TelemetryAgent,
    TelemetryRepository,
    TelemetryService,
    TelemetryValidator,
    register_telemetry_agent,
)
from config.config_manager import ConfigManager


class TestTelemetryAgentFramework(unittest.TestCase):

    def setUp(self):
        # Create temporary database file
        self.temp_db = tempfile.NamedTemporaryFile("w", delete=False, suffix=".db")
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        # Initialize schema and seed telemetry records
        self._seed_database()

        # Configure repositories & services
        self.repo = TelemetryRepository(db_path=self.temp_db_path)
        self.service = TelemetryService(repository=self.repo)
        self.event_bus = EventBus()
        self.container = ServiceContainer()
        self.registry = AgentRegistry(container=self.container)

        # Clear global state
        EventBus.get_global().clear()
        AgentRegistry.get_global().clear()
        ConfigManager.get_instance().reset_overrides()
        ConfigManager.get_instance().set_override("DB_PATH", self.temp_db_path)

    def tearDown(self):
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def _seed_database(self):
        """Seed sample telemetry records into temporary database."""
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
        # Seed records for Branch3-Uplink and Campus Core
        records = [
            (now - 100, "Branch3-Uplink", 45.0, 20.0, 2.5, 0.0, 0),
            (now - 50,  "Branch3-Uplink", 65.0, 45.0, 5.0, 1.0, 0),
            (now,       "Branch3-Uplink", 88.0, 120.0, 12.0, 3.0, 1),
            (now - 60,  "Campus Core",    55.0, 5.0, 1.2, 0.0, 0),
            (now,       "Campus Core",    58.0, 6.0, 1.5, 0.0, 0),
        ]

        cursor.executemany("""
            INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        conn.close()

    def test_01_telemetry_repository_queries(self):
        """Test TelemetryRepository queries against SQLite database."""
        # Latest record query
        latest = self.repo.get_latest_telemetry("Branch3-Uplink")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["utilization"], 88.0)
        self.assertEqual(latest["latency"], 120.0)

        # All latest records
        all_latest = self.repo.get_all_latest_telemetry()
        self.assertEqual(len(all_latest), 2)

        # Historical query
        hist = self.repo.get_historical_telemetry("Branch3-Uplink", limit=2)
        self.assertEqual(len(hist), 2)
        self.assertTrue(hist[0]["timestamp"] <= hist[1]["timestamp"])

        # Timerange query
        now = time.time()
        trange = self.repo.get_telemetry_by_timerange("Branch3-Uplink", now - 60, now + 10)
        self.assertEqual(len(trange), 2)

    def test_02_telemetry_validator(self):
        """Test TelemetryValidator validation rules and exception handling."""
        valid_raw = {
            "timestamp": time.time(),
            "interface": "Branch3-Uplink",
            "utilization": 50.0,
            "latency": 20.0,
            "jitter": 3.0,
            "drops": 0.0,
            "routing_flaps": 0,
        }
        validated = TelemetryValidator.validate_raw_record(valid_raw)
        self.assertEqual(validated["interface"], "Branch3-Uplink")

        # Invalid field types / bounds
        invalid_cases = [
            {**valid_raw, "utilization": 150.0},  # Utilization > 100
            {**valid_raw, "latency": -5.0},      # Latency < 0
            {**valid_raw, "interface": ""},       # Empty interface
            {**valid_raw, "routing_flaps": -1},   # Negative flaps
        ]

        for case in invalid_cases:
            with self.assertRaises(ValidationError):
                TelemetryValidator.validate_raw_record(case)

    def test_03_telemetry_service(self):
        """Test TelemetryService device resolution and TelemetryPacket creation."""
        # Device resolution
        did, dname = self.service.resolve_device("branch3-uplink")
        self.assertEqual(did, "branch3-uplink")
        self.assertEqual(dname, "Branch3-Uplink")

        # Fetch latest packet
        packet = self.service.fetch_latest_packet("Branch3-Uplink")
        self.assertIsNotNone(packet)
        self.assertIsInstance(packet, TelemetryPacket)
        self.assertEqual(packet.device_id, "branch3-uplink")
        self.assertEqual(packet.metrics["utilization"], 88.0)

        # Fetch all latest packets
        packets = self.service.fetch_all_latest_packets()
        self.assertEqual(len(packets), 2)

    def test_04_telemetry_agent_execution_and_events(self):
        """Test TelemetryAgent execution, EventBus publishing, and ExecutionContext."""
        received_events: List[Event] = []

        def event_handler(event: Event):
            received_events.append(event)

        self.event_bus.subscribe("telemetry.updated", event_handler)

        agent = TelemetryAgent(service=self.service, event_bus=self.event_bus)
        self.assertEqual(agent.name, "TelemetryAgent")

        # Execute agent for all devices
        ctx = ExecutionContext()
        packets = agent.execute({"device_id": "all", "mode": "latest"}, context=ctx)

        self.assertEqual(len(packets), 2)
        self.assertEqual(len(received_events), 2)

        # Check published event content
        evt = received_events[0]
        self.assertEqual(evt.event_type, "telemetry.updated")
        self.assertEqual(evt.source, "TelemetryAgent")
        self.assertIn("execution_id", evt.metadata)

        # Check execution context
        self.assertIn("TelemetryAgent", ctx.results)
        self.assertIn("Branch3-Uplink", ctx.shared_state["latest_telemetry"])

        # Check metrics update
        metrics = agent.metrics
        self.assertEqual(metrics.execution_count, 1)
        self.assertEqual(metrics.success_count, 1)

    def test_05_agent_registry_auto_registration(self):
        """Test automatic registration of TelemetryAgent in AgentRegistry."""
        agent = register_telemetry_agent(registry=self.registry)
        self.assertTrue(self.registry.exists("TelemetryAgent"))

        resolved = self.registry.get("TelemetryAgent")
        self.assertEqual(resolved, agent)

    def test_06_thread_safe_concurrent_execution(self):
        """Test thread safety under multi-threaded agent execution."""
        agent = TelemetryAgent(service=self.service, event_bus=self.event_bus)

        def worker_task(index: int):
            ctx = ExecutionContext()
            res = agent.execute({"device_id": "Branch3-Uplink", "mode": "latest"}, context=ctx)
            return len(res)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(10)]
            results = [f.result() for f in futures]

        self.assertEqual(results, [1] * 10)
        self.assertEqual(agent.metrics.execution_count, 10)
        self.assertEqual(agent.metrics.success_count, 10)


if __name__ == "__main__":
    unittest.main()
