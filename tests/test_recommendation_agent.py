"""
Comprehensive Unit Test Suite for Production RecommendationAgent, RecommendationService,
RecommendationRepository, RecommendationValidator, RecommendationRules, and RecommendationTemplateRegistry.
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
from agents.incident import IncidentAgent, register_incident_agent
from agents.prediction import PredictionAgent, register_prediction_agent
from agents.recommendation import (
    RecommendationAgent,
    RecommendationPriority,
    RecommendationRecord,
    RecommendationRepository,
    RecommendationRules,
    RecommendationService,
    RecommendationTemplateRegistry,
    RecommendationValidator,
    register_recommendation_agent,
)
from agents.registry import AgentRegistry
from agents.schemas import ExecutionContext
from agents.telemetry import TelemetryAgent
from config.config_manager import ConfigManager


class TestRecommendationAgentFramework(unittest.TestCase):

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

        self.repo = RecommendationRepository(db_path=self.temp_db_path)
        self.service = RecommendationService(repository=self.repo)
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
            u = 65.0 + (i * 1.0)  # Elevated utilization
            l = 30.0 + (i * 3.0)  # Elevated latency
            records.append((t, "Branch3-Uplink", u, l, 5.0, 1.0, 0))

        cursor.executemany("""
            INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        conn.close()

    def test_01_id_generation_and_repository(self):
        """Test sequential ID generation and SQLite recommendation repository persistence."""
        id1 = self.repo.generate_next_id()
        id2 = self.repo.generate_next_id()

        self.assertTrue(id1.startswith("REC-"))
        self.assertTrue(id2.startswith("REC-"))
        self.assertNotEqual(id1, id2)

        # Create recommendation
        inc_payload = {
            "incident_id": "INC-2026-000001",
            "device_id": "Branch3-Uplink",
            "interface": "Branch3-Uplink",
            "incident_type": "NETWORK_CONGESTION",
            "severity": "CRITICAL",
            "title": "[CRITICAL] Network Congestion on Branch3-Uplink",
        }
        rec = self.service.generate_recommendation_for_incident(inc_payload)

        self.assertIsNotNone(rec)
        self.assertTrue(rec.recommendation_id.startswith("REC-"))
        self.assertEqual(rec.priority, RecommendationPriority.CRITICAL)
        self.assertTrue(len(rec.execution_plan.actions) > 0)

        # Query recommendation
        fetched = self.repo.get_recommendation(rec.recommendation_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.recommendation_id, rec.recommendation_id)

    def test_02_templates_and_rules(self):
        """Test RecommendationTemplateRegistry and RecommendationRules formatting."""
        template = RecommendationTemplateRegistry.get_template("NETWORK_CONGESTION")
        self.assertIn("summary", template)
        self.assertTrue(len(template["actions"]) > 0)

        # Build formatted execution plan
        plan = RecommendationRules.build_execution_plan(template, "Branch3-Uplink")
        self.assertTrue(len(plan.actions) > 0)

        cmd = plan.actions[0].cli_commands[1]
        self.assertIn("Branch3-Uplink", cmd.command_text)
        self.assertTrue(cmd.is_reversable)

    def test_03_validator(self):
        """Test RecommendationValidator validation and exception checks."""
        inc_payload = {
            "incident_id": "INC-2026-000001",
            "device_id": "Branch3-Uplink",
            "interface": "Branch3-Uplink",
            "incident_type": "NETWORK_CONGESTION",
            "severity": "HIGH",
        }
        rec = self.service.generate_recommendation_for_incident(inc_payload)
        validated = RecommendationValidator.validate_recommendation_record(rec)
        self.assertEqual(validated.recommendation_id, rec.recommendation_id)

        # Invalid cases
        with self.assertRaises(ValidationError):
            RecommendationValidator.validate_incident_payload({"incident_id": ""})

    def test_04_recommendation_agent_direct_execution(self):
        """Test RecommendationAgent direct execution, EventBus publishing, and ExecutionContext."""
        generated_events: List[Event] = []

        def event_handler(evt: Event):
            generated_events.append(evt)

        self.event_bus.subscribe("recommendation.generated", event_handler)

        agent = RecommendationAgent(service=self.service, event_bus=self.event_bus)
        self.assertEqual(agent.name, "RecommendationAgent")

        inc_payload = {
            "incident_id": "INC-2026-000001",
            "device_id": "Branch3-Uplink",
            "interface": "Branch3-Uplink",
            "incident_type": "LATENCY_SPIKE",
            "severity": "HIGH",
        }

        ctx = ExecutionContext()
        recs = agent.execute(inc_payload, context=ctx)

        self.assertEqual(len(recs), 1)
        self.assertEqual(len(generated_events), 1)

        evt = generated_events[0]
        self.assertEqual(evt.event_type, "recommendation.generated")
        self.assertEqual(evt.source, "RecommendationAgent")
        self.assertIn("recommendation_id", evt.metadata)

        # Execution context check
        self.assertIn("RecommendationAgent", ctx.results)
        self.assertIn(recs[0].recommendation_id, ctx.shared_state["latest_recommendations"])

    def test_05_end_to_end_four_agent_event_pipeline(self):
        """Test full end-to-end multi-agent pipeline: Telemetry -> Prediction -> Incident -> Recommendation."""
        rec_events: List[Event] = []

        def rec_handler(evt: Event):
            rec_events.append(evt)

        bus = EventBus.get_global()
        bus.subscribe("recommendation.generated", rec_handler)

        # Register all 4 agents in global event bus
        telemetry_agent = TelemetryAgent(event_bus=bus)
        prediction_agent = register_prediction_agent(registry=self.registry)
        prediction_agent._event_bus = bus
        prediction_agent._setup_event_subscription()

        incident_agent = register_incident_agent(registry=self.registry)
        incident_agent._event_bus = bus
        incident_agent._setup_event_subscription()

        recommendation_agent = register_recommendation_agent(registry=self.registry)
        recommendation_agent._event_bus = bus
        recommendation_agent._setup_event_subscriptions()

        # Trigger TelemetryAgent
        telemetry_agent.execute({"device_id": "Branch3-Uplink", "mode": "latest"})

        # Verify full event cascade produced recommendation
        self.assertTrue(len(rec_events) >= 1)
        evt = rec_events[0]
        self.assertEqual(evt.event_type, "recommendation.generated")
        self.assertEqual(evt.source, "RecommendationAgent")
        self.assertIn("recommendation_id", evt.metadata)

    def test_06_thread_safe_concurrent_recommendation_generation(self):
        """Test multi-threaded concurrent execution of RecommendationAgent."""
        agent = RecommendationAgent(service=self.service, event_bus=self.event_bus)

        def worker_task(i: int):
            ctx = ExecutionContext()
            payload = {
                "incident_id": f"INC-2026-00000{i % 3 + 1}",
                "device_id": f"Device-{i % 3}",
                "interface": f"Device-{i % 3}",
                "incident_type": "NETWORK_CONGESTION",
                "severity": "HIGH",
            }
            res = agent.execute(payload, context=ctx)
            return len(res)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker_task, i) for i in range(10)]
            results = [f.result() for f in futures]

        self.assertEqual(results, [1] * 10)
        self.assertEqual(agent.metrics.execution_count, 10)
        self.assertEqual(agent.metrics.success_count, 10)


if __name__ == "__main__":
    unittest.main()
