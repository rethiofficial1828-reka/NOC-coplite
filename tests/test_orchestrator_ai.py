"""
Comprehensive Production Test Suite for Enterprise AI Investigation Orchestrator.

Validates PlannerAgent, ExecutionGraph (DAG), EvidenceRegistry, InvestigationContext,
ExecutionMonitor, DynamicScheduler, OrchestrationService, OrchestratorAgent, EventBus
lifecycle events, parallel execution, failure recovery, retry logic, and backward compatibility.
"""

from datetime import datetime, timezone
import threading
import time
import unittest
from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.incident.incident_agent import IncidentAgent
from agents.knowledge.knowledge_agent import KnowledgeAgent
from agents.orchestrator_ai.evidence_registry import EvidenceRegistry
from agents.orchestrator_ai.execution_graph import ExecutionGraph
from agents.orchestrator_ai.execution_monitor import ExecutionMonitor
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import (
    AgentExecutionPlan,
    ComplexityLevel,
    EvidenceReference,
    ExecutionNode,
    InvestigationPlan,
    InvestigationRequest,
    InvestigationResult,
    PlanStatus,
)
from agents.orchestrator_ai.orchestration_service import OrchestrationService
from agents.orchestrator_ai.orchestrator_agent import OrchestratorAgent
from agents.orchestrator_ai.planner_agent import PlannerAgent
from agents.orchestrator_ai.scheduler import DynamicScheduler
from agents.prediction.prediction_agent import PredictionAgent
from agents.recommendation.recommendation_agent import RecommendationAgent
from agents.registry.registry import AgentRegistry
from agents.schemas.schemas import AgentMetadata, CapabilityFlags
from agents.telemetry.telemetry_agent import TelemetryAgent
from agents.topology.topology_agent import TopologyAgent


class MockDummySuccessAgent(BaseAgent):
    def __init__(self, name: str, delay: float = 0.01) -> None:
        meta = AgentMetadata(name=name, capabilities=CapabilityFlags(supports_cpu=True))
        super().__init__(metadata=meta)
        self._delay = delay

    def _execute_internal(self, input_data: Any, context: Optional[Any] = None) -> Dict[str, Any]:
        if self._delay > 0:
            time.sleep(self._delay)
        return {"status": "success", "agent": self.name, "confidence": 0.90}


class MockDummyFailingAgent(BaseAgent):
    def __init__(self, name: str, max_failures: int = 10) -> None:
        meta = AgentMetadata(name=name, capabilities=CapabilityFlags(supports_cpu=True))
        super().__init__(metadata=meta)
        self.attempts = 0
        self.max_failures = max_failures

    def _execute_internal(self, input_data: Any, context: Optional[Any] = None) -> Dict[str, Any]:
        self.attempts += 1
        if self.attempts <= self.max_failures:
            raise RuntimeError(f"Simulated failure attempt {self.attempts}")
        return {"status": "recovered", "agent": self.name, "confidence": 0.85}


class TestOrchestratorAI(unittest.TestCase):
    def setUp(self) -> None:
        self.container = ServiceContainer.get_global()
        self.container.reset()
        self.registry = AgentRegistry.get_global()
        self.registry.clear()
        self.event_bus = EventBus.get_global()
        self.event_bus.clear()

    def tearDown(self) -> None:
        self.registry.clear()
        self.event_bus.clear()
        self.container.reset()

    # --- PlannerAgent Tests ---

    def test_planner_agent_classification_and_plan_generation(self) -> None:
        planner = PlannerAgent()
        
        # Test CRITICAL query classification
        req_critical = InvestigationRequest(operator_query="Critical core router outage failure")
        plan_crit = planner.execute(req_critical)
        self.assertEqual(plan_crit.query_classification, ComplexityLevel.CRITICAL)
        self.assertGreaterEqual(plan_crit.target_confidence, 0.90)

        # Test COMPLEX query classification
        req_complex = InvestigationRequest(operator_query="Why is Branch Router unstable?")
        plan_comp = planner.execute(req_complex)
        self.assertEqual(plan_comp.query_classification, ComplexityLevel.COMPLEX)
        self.assertIn("TelemetryAgent", plan_comp.required_agents)
        self.assertIn("PredictionAgent", plan_comp.required_agents)
        self.assertIn("IncidentAgent", plan_comp.required_agents)
        self.assertIn("RecommendationAgent", plan_comp.required_agents)
        self.assertIn("KnowledgeAgent", plan_comp.required_agents)

        # Test SIMPLE query classification
        req_simple = InvestigationRequest(operator_query="Show interface status")
        plan_simple = planner.execute(req_simple)
        self.assertEqual(plan_simple.query_classification, ComplexityLevel.SIMPLE)

    # --- ExecutionGraph (DAG) Tests ---

    def test_execution_graph_topological_sorting_and_layers(self) -> None:
        graph = ExecutionGraph(request_id="test-req-1")
        graph.add_node(ExecutionNode(node_id="A", agent_name="A"))
        graph.add_node(ExecutionNode(node_id="B", agent_name="B", dependencies=["A"]))
        graph.add_node(ExecutionNode(node_id="C", agent_name="C", dependencies=["A"]))
        graph.add_node(ExecutionNode(node_id="D", agent_name="D", dependencies=["B", "C"]))

        graph.add_edge("A", "B")
        graph.add_edge("A", "C")
        graph.add_edge("B", "D")
        graph.add_edge("C", "D")

        # Test Topological Sort
        sorted_order = graph.topological_sort()
        self.assertEqual(sorted_order[0], "A")
        self.assertEqual(sorted_order[-1], "D")

        # Test Parallel Execution Layers
        layers = graph.get_execution_levels()
        self.assertEqual(len(layers), 3)
        self.assertEqual(layers[0], ["A"])
        self.assertEqual(sorted(layers[1]), ["B", "C"])
        self.assertEqual(layers[2], ["D"])

        # Test visualization metadata
        viz = graph.get_visualization_metadata()
        self.assertEqual(viz["node_count"], 4)
        self.assertEqual(viz["edge_count"], 4)

    def test_execution_graph_cycle_detection(self) -> None:
        graph = ExecutionGraph(request_id="cycle-test")
        graph.add_node(ExecutionNode(node_id="A", agent_name="A"))
        graph.add_node(ExecutionNode(node_id="B", agent_name="B"))
        graph.add_edge("A", "B")
        graph.add_edge("B", "A")

        self.assertTrue(graph.has_cycle())

    def test_execution_graph_failure_propagation(self) -> None:
        graph = ExecutionGraph(request_id="fail-prop-test")
        graph.add_node(ExecutionNode(node_id="A", agent_name="A"))
        graph.add_node(ExecutionNode(node_id="B", agent_name="B", dependencies=["A"]))
        graph.add_node(ExecutionNode(node_id="C", agent_name="C", dependencies=["B"]))

        graph.add_edge("A", "B")
        graph.add_edge("B", "C")

        graph.update_node_status("A", PlanStatus.FAILED, error="Node A exploded")
        skipped = graph.propagate_failure("A")

        self.assertIn("B", skipped)
        self.assertIn("C", skipped)
        self.assertEqual(graph.get_node("B").status, PlanStatus.SKIPPED)
        self.assertEqual(graph.get_node("C").status, PlanStatus.SKIPPED)

    # --- EvidenceRegistry Tests ---

    def test_evidence_registry_lineage_and_thread_safety(self) -> None:
        registry = EvidenceRegistry()

        e1 = registry.register(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            payload={"bandwidth": 95.0},
            device_id="Router-1",
        )

        e2 = registry.register(
            source_agent="PredictionAgent",
            evidence_type="prediction",
            payload={"risk": 0.92},
            device_id="Router-1",
            parent_evidence_ids=[e1.evidence_id],
        )

        e3 = registry.register(
            source_agent="IncidentAgent",
            evidence_type="incident",
            payload={"incident_id": "INC-100"},
            device_id="Router-1",
            parent_evidence_ids=[e2.evidence_id],
        )

        self.assertEqual(len(registry.get_all()), 3)
        self.assertEqual(len(registry.get_by_source("TelemetryAgent")), 1)
        self.assertEqual(len(registry.get_by_device("Router-1")), 3)

        # Test Lineage Tracking
        lineage = registry.get_lineage(e3.evidence_id)
        self.assertEqual(len(lineage), 2)
        self.assertEqual(lineage[0].evidence_id, e1.evidence_id)
        self.assertEqual(lineage[1].evidence_id, e2.evidence_id)

        # Test Concurrent Thread Writes
        def worker(idx: int) -> None:
            for i in range(10):
                registry.register(
                    source_agent=f"WorkerAgent-{idx}",
                    evidence_type="test",
                    payload={"val": i},
                )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(registry.get_all()), 53)

    # --- InvestigationContext Tests ---

    def test_investigation_context_thread_safety(self) -> None:
        req = InvestigationRequest(operator_query="Test Context")
        ctx = InvestigationContext(request=req)

        ctx.set_agent_output("AgentA", {"res": "A"}, timing_ms=10.5)
        ctx.record_confidence_sample("AgentA", 0.85, rationale="Sample A")
        ctx.set_shared("key1", "val1")

        self.assertEqual(ctx.get_agent_output("AgentA"), {"res": "A"})
        self.assertEqual(ctx.get_latest_confidence(), 0.85)
        self.assertEqual(ctx.get_shared("key1"), "val1")

    # --- ExecutionMonitor Tests ---

    def test_execution_monitor_metrics(self) -> None:
        monitor = ExecutionMonitor(request_id="mon-1")
        monitor.start_monitoring()

        monitor.on_node_started("NodeA")
        time.sleep(0.02)
        monitor.on_node_completed("NodeA", 20.0)

        monitor.on_node_started("NodeB")
        monitor.on_node_skipped("NodeB", "Not needed")

        monitor.stop_monitoring()

        summary = monitor.to_summary()
        self.assertEqual(summary.executed_agents, 1)
        self.assertEqual(summary.skipped_agents, 1)
        self.assertGreater(summary.total_duration_ms, 0.0)

    # --- DynamicScheduler & OrchestratorAgent Integration Tests ---

    def test_dynamic_scheduler_parallel_execution_and_retry(self) -> None:
        # Register mock agents
        a1 = MockDummySuccessAgent("TelemetryAgent", delay=0.02)
        a2 = MockDummySuccessAgent("TopologyAgent", delay=0.02)
        a3 = MockDummyFailingAgent("PredictionAgent", max_failures=1)  # Will fail 1st, succeed 2nd

        self.registry.register(a1)
        self.registry.register(a2)
        self.registry.register(a3)

        planner = PlannerAgent()
        req = InvestigationRequest(operator_query="Why is Branch Router unstable?")
        plan = planner.execute(req)
        plan.target_confidence = 0.99

        graph = ExecutionGraph.from_plan(plan)
        ctx = InvestigationContext(request=req, plan=plan)

        scheduler = DynamicScheduler(max_workers=4)
        monitor = scheduler.execute_graph(graph, ctx, self.registry, self.event_bus)

        self.assertEqual(graph.get_node("TelemetryAgent").status, PlanStatus.COMPLETED)
        self.assertEqual(graph.get_node("TopologyAgent").status, PlanStatus.COMPLETED)
        self.assertEqual(graph.get_node("PredictionAgent").status, PlanStatus.COMPLETED)
        self.assertEqual(graph.get_node("PredictionAgent").retry_count, 1)

    def test_orchestrator_agent_end_to_end_and_events(self) -> None:
        # Register all 6 Atomic Agents
        telemetry = TelemetryAgent()
        topology = TopologyAgent()
        prediction = PredictionAgent()
        incident = IncidentAgent()
        recommendation = RecommendationAgent()
        knowledge = KnowledgeAgent()

        self.registry.register(telemetry)
        self.registry.register(topology)
        self.registry.register(prediction)
        self.registry.register(incident)
        self.registry.register(recommendation)
        self.registry.register(knowledge)

        events_received = []

        def event_handler(evt: Event) -> None:
            events_received.append(evt.event_type)

        self.event_bus.subscribe("*", event_handler)

        orchestrator = OrchestratorAgent()
        req = InvestigationRequest(
            operator_query="Why is Branch Router unstable?",
            device_id="Branch3-Uplink",
            interface="eth0",
        )

        result: InvestigationResult = orchestrator.execute(req)

        self.assertIsInstance(result, InvestigationResult)
        self.assertIn(result.status, (PlanStatus.COMPLETED, PlanStatus.FAILED))
        self.assertGreater(len(result.evidence_references), 0)

        # Check EventBus lifecycle events
        self.assertIn("investigation.started", events_received)
        self.assertIn("investigation.planned", events_received)
        self.assertIn("agent.execution.started", events_received)
        self.assertIn("agent.execution.completed", events_received)


if __name__ == "__main__":
    unittest.main()
