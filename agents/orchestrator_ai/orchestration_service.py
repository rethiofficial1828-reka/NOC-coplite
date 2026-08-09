"""
Orchestration Service for Enterprise AI Investigation Platform.

Coordinates planning, DAG graph generation, execution scheduling, evidence registration,
output merging, confidence scoring, and executive summary generation.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from agents.core.container import ServiceContainer
from agents.core.logger import get_agent_logger
from agents.events.event_bus import EventBus
from agents.orchestrator_ai.evidence_registry import EvidenceRegistry
from agents.orchestrator_ai.execution_graph import ExecutionGraph
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import (
    InvestigationPlan,
    InvestigationRequest,
    InvestigationResult,
    PlanStatus,
)
from agents.orchestrator_ai.planner_agent import PlannerAgent
from agents.orchestrator_ai.scheduler import DynamicScheduler
from agents.registry.registry import AgentRegistry

logger = get_agent_logger("OrchestrationService")


class OrchestrationService:
    """
    Domain service orchestrating end-to-end AI network investigation workflows.
    """

    def __init__(
        self,
        planner: Optional[PlannerAgent] = None,
        scheduler: Optional[DynamicScheduler] = None,
        registry: Optional[AgentRegistry] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._planner = planner or PlannerAgent()
        self._scheduler = scheduler or DynamicScheduler()
        self._registry = registry or AgentRegistry.get_global()
        self._event_bus = event_bus or EventBus.get_global()
        self._lock = threading.RLock()

    def orchestrate(
        self,
        request: InvestigationRequest,
        context: Optional[InvestigationContext] = None,
    ) -> InvestigationResult:
        """
        Execute end-to-end investigation workflow for an InvestigationRequest.

        Args:
            request: Operator investigation request payload.
            context: Optional pre-constructed InvestigationContext.

        Returns:
            Completed InvestigationResult payload.
        """
        with self._lock:
            ctx = context or InvestigationContext(request=request)
            
            # Step 1: Generate InvestigationPlan using PlannerAgent
            plan: InvestigationPlan = self._planner.execute(request, ctx)
            ctx.plan = plan

            # Step 2: Build ExecutionGraph DAG from plan
            graph = ExecutionGraph.from_plan(plan)

            # Step 3: Execute DAG using DynamicScheduler
            monitor = self._scheduler.execute_graph(
                graph=graph,
                context=ctx,
                agent_registry=self._registry,
                event_bus=self._event_bus,
            )

            # Step 4: Evaluate overall status
            nodes = graph.nodes
            failed_nodes = [n for n in nodes.values() if n.status == PlanStatus.FAILED and n.mandatory]
            final_status = PlanStatus.FAILED if failed_nodes else PlanStatus.COMPLETED

            # Step 5: Merge evidence, compute confidence, generate summary
            evidence_refs = ctx.evidence_registry.get_all()
            merged_findings = self.merge_outputs(ctx)
            overall_confidence = self.calculate_overall_confidence(ctx)
            summary_text = self.generate_executive_summary(ctx, final_status)

            result = InvestigationResult(
                investigation_id=ctx.context_id,
                request_id=request.request_id,
                plan_id=plan.plan_id,
                status=final_status,
                summary=summary_text,
                evidence_references=evidence_refs,
                merged_findings=merged_findings,
                agent_outputs=ctx.get_all_agent_outputs(),
                execution_summary=monitor.to_summary(),
                overall_confidence=overall_confidence,
                created_at=request.created_at,
                completed_at=datetime.now(timezone.utc),
            )

            logger.info(
                f"OrchestrationService completed request '{request.request_id}' with status {final_status.value} "
                f"(confidence={overall_confidence:.2f}, evidence_items={len(evidence_refs)})"
            )
            return result

    def merge_outputs(self, context: InvestigationContext) -> Dict[str, Any]:
        """
        Merge individual Atomic Agent outputs into a unified findings dictionary.
        """
        outputs = context.get_all_agent_outputs()
        merged: Dict[str, Any] = {
            "telemetry_summary": None,
            "risk_assessment": None,
            "active_incidents": [],
            "recommendations": [],
            "topology_context": None,
            "rag_runbooks": [],
        }

        for agent_name, raw_out in outputs.items():
            if agent_name == "TelemetryAgent":
                merged["telemetry_summary"] = raw_out
            elif agent_name == "PredictionAgent":
                merged["risk_assessment"] = raw_out
            elif agent_name == "IncidentAgent":
                merged["active_incidents"].append(raw_out)
            elif agent_name == "RecommendationAgent":
                merged["recommendations"].append(raw_out)
            elif agent_name == "TopologyAgent":
                merged["topology_context"] = raw_out
            elif agent_name == "KnowledgeAgent":
                merged["rag_runbooks"].append(raw_out)

        return merged

    def calculate_overall_confidence(self, context: InvestigationContext) -> float:
        """
        Calculate weighted composite confidence score based on collected evidence.
        """
        evidence_list = context.evidence_registry.get_all()
        if not evidence_list:
            return 0.0

        total_weight = sum(e.confidence for e in evidence_list)
        return max(0.0, min(1.0, total_weight / len(evidence_list)))

    def generate_executive_summary(self, context: InvestigationContext, status: PlanStatus) -> str:
        """
        Synthesize human-readable executive summary string for network operators.
        """
        req = context.request
        plan = context.plan
        evidence_count = len(context.evidence_registry.get_all())

        if status == PlanStatus.COMPLETED:
            return (
                f"Investigation for query '{req.operator_query}' completed successfully. "
                f"Executed {len(plan.required_agents) if plan else 0} agents across DAG pipeline, "
                f"collecting {evidence_count} evidence references with target confidence achieved."
            )
        else:
            return (
                f"Investigation for query '{req.operator_query}' encountered failure during execution. "
                f"Collected {evidence_count} evidence references prior to failure."
            )
