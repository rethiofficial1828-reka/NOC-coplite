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
    EvidenceProvenance,
    EvidenceReference,
    EvidenceRelationship,
    ExecutionNode,
    InvestigationEvidenceLineage,
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


# ===========================================================================
# Phase 2: Evidence-Centric Cross-Agent Investigation Tests
# ===========================================================================


class TestEvidenceLineageCrossAgent(unittest.TestCase):
    """
    Tests for EvidenceReference enhancement, EvidenceRegistry query helpers,
    and InvestigationContext.build_evidence_lineage.
    """

    def setUp(self) -> None:
        self.registry = EvidenceRegistry()
        self.req = InvestigationRequest(
            operator_query="Investigate Branch3-Uplink degradation",
            device_id="Branch3-Uplink",
        )
        self.ctx = InvestigationContext(request=self.req, evidence_registry=self.registry)

    def test_01_explicit_provenance_registration(self) -> None:
        """Registering items with all controlled provenance labels succeeds."""
        e1 = self.registry.register(
            source_agent="TelemetryAgent",
            evidence_type="telemetry",
            payload={"util": 90.0},
            provenance="OBSERVED",
            relationship="SUPPORTING",
        )
        e2 = self.registry.register(
            source_agent="PredictionAgent",
            evidence_type="prediction",
            payload={"risk": 0.85},
            provenance="PREDICTED",
            relationship="SUPPORTING",
        )
        e3 = self.registry.register(
            source_agent="ReasoningAgent",
            evidence_type="reasoning",
            payload={"cause": "Congestion"},
            provenance="INFERRED",
            relationship="SUPPORTING",
        )
        e4 = self.registry.register(
            source_agent="KnowledgeAgent",
            evidence_type="knowledge",
            payload={"pattern": "WAN-01"},
            provenance="HISTORICAL",
            relationship="NEUTRAL",
        )
        e5 = self.registry.register(
            source_agent="PathDecisionService",
            evidence_type="path_decision",
            payload={"candidate": "ISP-B"},
            provenance="SIMULATION",
            relationship="SUPPORTING",
        )

        self.assertEqual(e1.provenance, "OBSERVED")
        self.assertEqual(e2.provenance, "PREDICTED")
        self.assertEqual(e3.provenance, "INFERRED")
        self.assertEqual(e4.provenance, "HISTORICAL")
        self.assertEqual(e5.provenance, "SIMULATION")

    def test_02_relationship_classification(self) -> None:
        """Counts for SUPPORTING, CONTRADICTING, UNRESOLVED, and NEUTRAL are strictly partitioned."""
        self.registry.register(source_agent="A1", evidence_type="t1", payload={}, relationship="SUPPORTING")
        self.registry.register(source_agent="A2", evidence_type="t2", payload={}, relationship="SUPPORTING")
        self.registry.register(source_agent="A3", evidence_type="t3", payload={}, relationship="CONTRADICTING")
        self.registry.register(source_agent="A4", evidence_type="t4", payload={}, relationship="UNRESOLVED")
        self.registry.register(source_agent="A5", evidence_type="t5", payload={}, relationship="NEUTRAL")

        lineage = self.ctx.build_evidence_lineage(auto_ingest_subsystems=False)
        self.assertEqual(lineage.evidence_count, 5)
        self.assertEqual(lineage.supporting_count, 2)
        self.assertEqual(lineage.contradicting_count, 1)
        self.assertEqual(lineage.unresolved_count, 1)

    def test_03_linked_decision_preservation(self) -> None:
        """Linked decision tags are retained on evidence items and queryable."""
        decision_str = "HUMAN_APPROVAL_REQUIRED"
        e = self.registry.register(
            source_agent="TrustService",
            evidence_type="trust",
            payload={"score": 0.52},
            linked_decision=decision_str,
            summary="Trust Gate required human review",
        )
        self.assertEqual(e.linked_decision, decision_str)
        matched = self.registry.get_by_linked_decision(decision_str)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].evidence_id, e.evidence_id)

    def test_04_provenance_preservation(self) -> None:
        """Lineage report retains exact provenance labels across all timeline entries."""
        self.registry.register(source_agent="TelemetryAgent", evidence_type="telemetry", payload={}, provenance="OBSERVED")
        self.registry.register(source_agent="PredictionAgent", evidence_type="prediction", payload={}, provenance="PREDICTED")
        self.registry.register(source_agent="IncidentAgent", evidence_type="incident", payload={}, provenance="INFERRED")

        lineage = self.ctx.build_evidence_lineage(auto_ingest_subsystems=False)
        provenances = [item.provenance for item in lineage.timeline]
        self.assertIn("OBSERVED", provenances)
        self.assertIn("PREDICTED", provenances)
        self.assertIn("INFERRED", provenances)

    def test_05_filter_helpers(self) -> None:
        """Read-only query helpers get_by_relationship, get_by_provenance, get_by_linked_decision filter accurately."""
        self.registry.register(source_agent="T1", evidence_type="tel", payload={}, provenance="OBSERVED", relationship="SUPPORTING", linked_decision="DEC-1")
        self.registry.register(source_agent="P1", evidence_type="pred", payload={}, provenance="PREDICTED", relationship="CONTRADICTING", linked_decision="DEC-2")
        self.registry.register(source_agent="R1", evidence_type="reas", payload={}, provenance="INFERRED", relationship="SUPPORTING", linked_decision="DEC-1")

        self.assertEqual(len(self.registry.get_by_relationship("SUPPORTING")), 2)
        self.assertEqual(len(self.registry.get_by_relationship("CONTRADICTING")), 1)
        self.assertEqual(len(self.registry.get_by_provenance("OBSERVED")), 1)
        self.assertEqual(len(self.registry.get_by_provenance("INFERRED")), 1)
        self.assertEqual(len(self.registry.get_by_linked_decision("DEC-1")), 2)
        self.assertEqual(len(self.registry.get_by_linked_decision("DEC-2")), 1)

    def test_06_topology_evidence_integration(self) -> None:
        """Topology impact assessment evidence integrates into the unified lineage report."""
        self.registry.register(
            source_agent="TopologyService",
            evidence_type="topology",
            payload={"blast_radius": "CRITICAL", "impact_pct": 83.33, "spofs": ["branch3-uplink", "fw-01"]},
            confidence=1.0,
            provenance="INFERRED",
            relationship="SUPPORTING",
            affected_entity="Branch3-Uplink",
            linked_decision="Blast Radius: CRITICAL (83.3%)",
            summary="Topology graph identified critical blast radius and SPOF dependencies.",
        )
        lineage = self.ctx.build_evidence_lineage("Branch3-Uplink", auto_ingest_subsystems=False)
        self.assertTrue(any(e.source_agent == "TopologyService" for e in lineage.timeline))
        self.assertTrue(any(d["stage"] == "Topology Blast Radius & SPOF" for d in lineage.decision_linkages))

    def test_07_decision_to_evidence_linkage(self) -> None:
        """Decision linkages map investigation pipeline stages to exact originating evidence IDs."""
        self.ctx.set_agent_output("TelemetryAgent", {"util": 85.0, "confidence": 1.0})
        self.ctx.set_agent_output("PredictionAgent", {"risk": 0.88, "confidence": 0.88})
        self.ctx.set_agent_output("TrustAgent", {"decision": "HUMAN_APPROVAL_REQUIRED", "confidence": 0.52})

        lineage = self.ctx.build_evidence_lineage(auto_ingest_subsystems=True)
        self.assertTrue(len(lineage.decision_linkages) >= 3)
        for link in lineage.decision_linkages:
            self.assertIn("stage", link)
            self.assertIn("provenance", link)
            self.assertIn("decision", link)
            self.assertGreater(len(link["evidence_ids"]), 0)

    def test_08_missing_unresolvable_evidence_handling(self) -> None:
        """Empty context or unresolved target returns a valid typed lineage report without raising."""
        empty_ctx = InvestigationContext(request=InvestigationRequest(operator_query="Empty"))
        lineage = empty_ctx.build_evidence_lineage(target_entity="NonExistent", auto_ingest_subsystems=False)
        self.assertIsInstance(lineage, InvestigationEvidenceLineage)
        self.assertEqual(lineage.evidence_count, 0)
        self.assertEqual(lineage.supporting_count, 0)
        self.assertEqual(lineage.contradicting_count, 0)
        self.assertEqual(lineage.top_contributors, [])

    def test_09_readonly_nonmutating_behavior(self) -> None:
        """Building evidence lineage is strictly read-only and does not mutate external state."""
        self.registry.register(source_agent="TelemetryAgent", evidence_type="telemetry", payload={"loss": 0.02})
        count_before = len(self.registry.get_all())

        _ = self.ctx.build_evidence_lineage("Branch3-Uplink", auto_ingest_subsystems=False)
        _ = self.ctx.build_evidence_lineage("Branch3-Uplink", auto_ingest_subsystems=False)

        count_after = len(self.registry.get_all())
        self.assertEqual(count_before, count_after)

    def test_10_no_duplicate_evidence_registration(self) -> None:
        """Auto-ingest subsystems does not register duplicate items on repeated calls."""
        self.ctx.set_agent_output("TelemetryAgent", {"util": 88.0})
        self.ctx.set_agent_output("PredictionAgent", {"risk": 0.85})

        lineage1 = self.ctx.build_evidence_lineage(auto_ingest_subsystems=True)
        count1 = lineage1.evidence_count

        lineage2 = self.ctx.build_evidence_lineage(auto_ingest_subsystems=True)
        count2 = lineage2.evidence_count

        self.assertEqual(count1, count2)


if __name__ == "__main__":
    unittest.main()

