"""
Comprehensive Unit Test Suite for Production KnowledgeAgent, KnowledgeService,
KnowledgeRepository, KnowledgeValidator, KnowledgePromptBuilder, KnowledgeCache,
LLMProvider, and MockProvider.
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
from agents.incident import register_incident_agent
from agents.knowledge import (
    KnowledgeAgent,
    KnowledgeCache,
    KnowledgePromptBuilder,
    KnowledgeRepository,
    KnowledgeResult,
    KnowledgeService,
    KnowledgeValidator,
    MockProvider,
    register_knowledge_agent,
)
from agents.prediction import register_prediction_agent
from agents.recommendation import register_recommendation_agent
from agents.registry import AgentRegistry
from agents.schemas import ExecutionContext
from agents.telemetry import TelemetryAgent
from config.config_manager import ConfigManager


class TestKnowledgeAgentFramework(unittest.TestCase):

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

        self.repo = KnowledgeRepository(db_path=self.temp_db_path)
        self.provider = MockProvider()
        self.service = KnowledgeService(provider=self.provider, repository=self.repo)
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
            u = 70.0 + (i * 1.0)
            l = 35.0 + (i * 3.0)
            records.append((t, "Branch3-Uplink", u, l, 5.0, 1.0, 0))

        cursor.executemany("""
            INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        conn.close()

    def test_01_mock_provider_and_cache(self):
        """Test MockProvider interface responses and KnowledgeCache hit/miss behavior."""
        provider = MockProvider()
        provider.initialize()
        self.assertEqual(provider.health()["status"], "ok")
        self.assertEqual(provider.metadata()["provider_name"], "MockProvider")

        prompt = "Explain congestion on Branch3-Uplink"
        res_text = provider.generate(prompt)
        self.assertIn("ROOT CAUSE ANALYSIS", res_text)

        # Test cache
        cache = KnowledgeCache(default_ttl_seconds=60.0)
        self.assertIsNone(cache.get("key1"))

        dummy_result = KnowledgeResult(
            result_id="KNOW-2026-000001",
            query_id="q1",
            recommendation_id="REC-2026-000001",
            incident_id="INC-2026-000001",
            device_id="Branch3-Uplink",
            generated_explanation="Test explanation",
            confidence_score=0.90,
        )
        cache.set("key1", dummy_result)
        self.assertEqual(cache.get("key1").result_id, "KNOW-2026-000001")

    def test_02_prompt_builder_and_repository(self):
        """Test KnowledgePromptBuilder formatting and KnowledgeRepository database queries."""
        inc = {"incident_id": "INC-1", "title": "Congestion", "severity": "HIGH", "risk_score": 0.80}
        rec = {"recommendation_id": "REC-1", "summary": "Apply QoS", "priority": "HIGH"}

        prompt = KnowledgePromptBuilder.build_prompt(inc, rec)
        self.assertIn("INC-1", prompt)
        self.assertIn("REC-1", prompt)

        # Repository ID generation
        id1 = self.repo.generate_next_id()
        self.assertTrue(id1.startswith("KNOW-"))

    def test_03_knowledge_validator(self):
        """Test KnowledgeValidator schema bounds and error checks."""
        valid_res = KnowledgeResult(
            result_id="KNOW-2026-000001",
            query_id="q1",
            recommendation_id="REC-2026-000001",
            incident_id="INC-2026-000001",
            device_id="Branch3-Uplink",
            generated_explanation="Valid explanation",
            confidence_score=0.88,
        )
        validated = KnowledgeValidator.validate_knowledge_result(valid_res)
        self.assertEqual(validated.result_id, "KNOW-2026-000001")

        # Invalid cases
        with self.assertRaises(ValidationError):
            KnowledgeValidator.validate_recommendation_payload({"recommendation_id": ""})

    def test_04_knowledge_agent_execution_and_events(self):
        """Test KnowledgeAgent direct execution, EventBus publishing, and ExecutionContext."""
        generated_events: List[Event] = []

        def event_handler(evt: Event):
            generated_events.append(evt)

        self.event_bus.subscribe("knowledge.generated", event_handler)

        agent = KnowledgeAgent(service=self.service, event_bus=self.event_bus)
        self.assertEqual(agent.name, "KnowledgeAgent")

        rec_payload = {
            "recommendation_id": "REC-2026-000001",
            "incident_id": "INC-2026-000001",
            "device_id": "Branch3-Uplink",
            "interface": "Branch3-Uplink",
            "summary": "Apply QoS bandwidth shaping",
            "priority": "HIGH",
        }

        ctx = ExecutionContext()
        results = agent.execute(rec_payload, context=ctx)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(generated_events), 1)

        evt = generated_events[0]
        self.assertEqual(evt.event_type, "knowledge.generated")
        self.assertEqual(evt.source, "KnowledgeAgent")
        self.assertIn("result_id", evt.metadata)

        # Context check
        self.assertIn("KnowledgeAgent", ctx.results)
        self.assertIn(results[0].result_id, ctx.shared_state["latest_knowledge"])

    def test_05_full_five_agent_pipeline(self):
        """Test full 5-agent reactive event pipeline: Telemetry -> Prediction -> Incident -> Recommendation -> Knowledge."""
        know_events: List[Event] = []

        def know_handler(evt: Event):
            know_events.append(evt)

        bus = EventBus.get_global()
        bus.subscribe("knowledge.generated", know_handler)

        # Register all 5 agents
        telemetry_agent = TelemetryAgent(event_bus=bus)

        pred_agent = register_prediction_agent(registry=self.registry)
        pred_agent._event_bus = bus
        pred_agent._setup_event_subscription()

        inc_agent = register_incident_agent(registry=self.registry)
        inc_agent._event_bus = bus
        inc_agent._setup_event_subscription()

        rec_agent = register_recommendation_agent(registry=self.registry)
        rec_agent._event_bus = bus
        rec_agent._setup_event_subscriptions()

        know_agent = register_knowledge_agent(registry=self.registry)
        know_agent._event_bus = bus
        know_agent._setup_event_subscription()

        # Trigger TelemetryAgent
        telemetry_agent.execute({"device_id": "Branch3-Uplink", "mode": "latest"})

        # Assert KnowledgeAgent produced knowledge.generated event via full event chain
        self.assertTrue(len(know_events) >= 1)
        evt = know_events[0]
        self.assertEqual(evt.event_type, "knowledge.generated")
        self.assertEqual(evt.source, "KnowledgeAgent")
        self.assertIn("result_id", evt.metadata)

    def test_06_thread_safe_concurrent_knowledge_generation(self):
        """Test multi-threaded concurrent execution of KnowledgeAgent."""
        agent = KnowledgeAgent(service=self.service, event_bus=self.event_bus)

        def worker_task(i: int):
            ctx = ExecutionContext()
            payload = {
                "recommendation_id": f"REC-2026-00000{i % 3 + 1}",
                "incident_id": f"INC-2026-00000{i % 3 + 1}",
                "device_id": f"Device-{i % 3}",
                "interface": f"Device-{i % 3}",
                "summary": "Apply bandwidth shaping",
                "priority": "HIGH",
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
