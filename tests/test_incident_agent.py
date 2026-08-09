"""
Comprehensive Unit Test Suite for Production IncidentAgent, IncidentService,
IncidentRepository, IncidentValidator, IncidentRules, and IncidentStateMachine.
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
from agents.incident import (
    IncidentAgent,
    IncidentRecord,
    IncidentRepository,
    IncidentRules,
    IncidentService,
    IncidentSeverity,
    IncidentStateMachine,
    IncidentStatus,
    IncidentValidator,
    register_incident_agent,
)
from agents.prediction import PredictionAgent, PredictionRepository, PredictionService, register_prediction_agent
from agents.registry import AgentRegistry
from agents.schemas import ExecutionContext, PredictionResult
from agents.telemetry import TelemetryAgent, TelemetryRepository, TelemetryService
from config.config_manager import ConfigManager


class TestIncidentAgentFramework(unittest.TestCase):

    def setUp(self):
        # Create temporary database file
        self.temp_db = tempfile.NamedTemporaryFile("w", delete=False, suffix=".db")
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()

        # Seed telemetry database
        self._seed_database()

        # Configure overrides & instances
        ConfigManager.get_instance().reset_overrides()
        ConfigManager.get_instance().set_override("DB_PATH", self.temp_db_path)

        self.repo = IncidentRepository(db_path=self.temp_db_path)
        self.service = IncidentService(repository=self.repo)
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
        """Seed sample telemetry records for testing pipeline."""
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
            u = 60.0 + (i * 1.2)  # Ramp up to elevated utilization
            l = 25.0 + (i * 3.5)  # Ramp up to high latency
            records.append((t, "Branch3-Uplink", u, l, 5.0, 1.0, 0))

        cursor.executemany("""
            INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        conn.close()

    def test_01_incident_id_generation_and_repository(self):
        """Test sequential ID generation and SQLite incident repository persistence."""
        id1 = self.repo.generate_next_id()
        id2 = self.repo.generate_next_id()

        self.assertTrue(id1.startswith("INC-"))
        self.assertTrue(id2.startswith("INC-"))
        self.assertNotEqual(id1, id2)

        # Create incident
        pred = {"interface": "Branch3-Uplink", "risk_score": 0.88, "time_to_impact": 8.0, "contributing_signals": ["utilization elevated"]}
        inc, action = self.service.process_prediction(pred)

        self.assertIsNotNone(inc)
        self.assertEqual(action, "created")
        self.assertEqual(inc.severity, IncidentSeverity.CRITICAL)

        # Query incident
        fetched = self.repo.get_incident(inc.incident_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.incident_id, inc.incident_id)
        self.assertEqual(fetched.severity, IncidentSeverity.CRITICAL)

    def test_02_incident_rules_and_severity_mapping(self):
        """Test IncidentRules risk-to-severity mapping and classification."""
        self.assertEqual(IncidentRules.map_risk_to_severity(0.90), IncidentSeverity.CRITICAL)
        self.assertEqual(IncidentRules.map_risk_to_severity(0.75), IncidentSeverity.HIGH)
        self.assertEqual(IncidentRules.map_risk_to_severity(0.50), IncidentSeverity.MEDIUM)
        self.assertEqual(IncidentRules.map_risk_to_severity(0.30), IncidentSeverity.LOW)
        self.assertEqual(IncidentRules.map_risk_to_severity(0.10), IncidentSeverity.INFO)

        # Incident type classification
        self.assertEqual(IncidentRules.determine_incident_type(["egress drops starting"]), "EGRESS_PACKET_DROPS")
        self.assertEqual(IncidentRules.determine_incident_type(["routing instability detected"]), "ROUTING_INSTABILITY")
        self.assertEqual(IncidentRules.determine_incident_type(["latency trending up"]), "LATENCY_SPIKE")
        self.assertEqual(IncidentRules.determine_incident_type(["utilization rising"]), "NETWORK_CONGESTION")

    def test_03_incident_state_machine_transitions(self):
        """Test IncidentStateMachine transition rules and forbidden transition validation."""
        inc_id = self.repo.generate_next_id()
        inc = IncidentRecord(
            incident_id=inc_id,
            device_id="Branch3-Uplink",
            interface="Branch3-Uplink",
            title="Test Incident",
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.NEW,
        )

        # Valid transitions
        IncidentStateMachine.transition(inc, IncidentStatus.OPEN)
        self.assertEqual(inc.status, IncidentStatus.OPEN)

        IncidentStateMachine.transition(inc, IncidentStatus.ACKNOWLEDGED)
        self.assertEqual(inc.status, IncidentStatus.ACKNOWLEDGED)

        IncidentStateMachine.transition(inc, IncidentStatus.RESOLVED)
        self.assertEqual(inc.status, IncidentStatus.RESOLVED)
        self.assertIsNotNone(inc.resolved_at)

        # Forbidden transition test (NEW -> RESOLVED is invalid directly)
        new_inc = IncidentRecord(
            incident_id=self.repo.generate_next_id(),
            device_id="Branch3-Uplink",
            interface="Branch3-Uplink",
            title="Invalid Transition Incident",
            status=IncidentStatus.NEW,
        )
        with self.assertRaises(ValidationError):
            IncidentStateMachine.transition(new_inc, IncidentStatus.RESOLVED)

    def test_04_incident_deduplication_and_auto_resolution(self):
        """Test deduplication logic updating active incidents and auto-resolving upon recovery."""
        pred_high = {"interface": "Branch3-Uplink", "risk_score": 0.50, "contributing_signals": ["utilization rising"]}

        # First prediction creates incident
        inc1, action1 = self.service.process_prediction(pred_high)
        self.assertEqual(action1, "created")
        self.assertEqual(inc1.status, IncidentStatus.OPEN)

        # Second prediction for same device updates existing active incident (Deduplication)
        pred_escalated = {"interface": "Branch3-Uplink", "risk_score": 0.90, "contributing_signals": ["utilization rising"]}
        inc2, action2 = self.service.process_prediction(pred_escalated)

        self.assertEqual(inc1.incident_id, inc2.incident_id)
        self.assertEqual(action2, "severity_changed")
        self.assertEqual(inc2.severity, IncidentSeverity.CRITICAL)

        # Third prediction with low risk score auto-resolves active incident
        pred_recovered = {"interface": "Branch3-Uplink", "risk_score": 0.10, "contributing_signals": []}
        inc3, action3 = self.service.process_prediction(pred_recovered)

        self.assertEqual(inc1.incident_id, inc3.incident_id)
        self.assertEqual(action3, "resolved")
        self.assertEqual(inc3.status, IncidentStatus.RESOLVED)

    def test_05_incident_agent_reactive_pipeline(self):
        """Test reactive multi-agent event pipeline: Telemetry -> Prediction -> Incident Agent."""
        created_events: List[Event] = []

        def incident_event_handler(evt: Event):
            created_events.append(evt)

        # Global event bus setup
        bus = EventBus.get_global()
        bus.subscribe("incident.created", incident_event_handler)
        bus.subscribe("incident.severity_changed", incident_event_handler)

        # Setup Agents
        telemetry_agent = TelemetryAgent(event_bus=bus)
        prediction_agent = register_prediction_agent(registry=self.registry)
        prediction_agent._event_bus = bus
        prediction_agent._setup_event_subscription()

        incident_agent = register_incident_agent(registry=self.registry)
        incident_agent._event_bus = bus
        incident_agent._setup_event_subscription()

        # Run TelemetryAgent
        telemetry_agent.execute({"device_id": "Branch3-Uplink", "mode": "latest"})

        # Verify event propagation through all 3 agents
        self.assertTrue(len(created_events) >= 1)
        evt = created_events[0]
        self.assertIn(evt.event_type, ("incident.created", "incident.severity_changed"))
        self.assertEqual(evt.source, "IncidentAgent")
        self.assertIn("incident_id", evt.metadata)

    def test_06_thread_safe_concurrent_incident_processing(self):
        """Test thread safety under multi-threaded execution."""
        agent = IncidentAgent(service=self.service, event_bus=self.event_bus)

        def worker_task(i: int):
            ctx = ExecutionContext()
            pred = {"interface": f"Device-{i % 3}", "risk_score": 0.75, "contributing_signals": ["utilization elevated"]}
            res = agent.execute(pred, context=ctx)
            return len(res)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(10)]
            results = [f.result() for f in futures]

        self.assertEqual(results, [1] * 10)
        self.assertEqual(agent.metrics.execution_count, 10)
        self.assertEqual(agent.metrics.success_count, 10)


if __name__ == "__main__":
    unittest.main()
