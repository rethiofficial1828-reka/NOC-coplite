"""
Planner Agent for Enterprise AI Investigation Platform.

Analyzes operator intent, classifies query complexity, determines evidence requirements
and required Atomic Agents, estimates execution cost and target confidence, and constructs
a structured InvestigationPlan.

CRITICAL PRINCIPLE: PlannerAgent performs planning only. It never fetches operational data directly.
"""

from typing import Any, Dict, List, Optional
import uuid

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ValidationError
from agents.events.event_bus import EventBus
from agents.orchestrator_ai.investigation_models import (
    AgentExecutionPlan,
    ComplexityLevel,
    InvestigationPlan,
    InvestigationRequest,
)
from agents.orchestrator_ai.investigation_plan import InvestigationPlanBuilder
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class PlannerAgent(BaseAgent):
    """
    Atomic Agent responsible for analyzing operator intent and generating InvestigationPlans.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        default_meta = AgentMetadata(
            name="PlannerAgent",
            version="1.0.0",
            description="AI Planner agent that decomposes operator queries into DAG investigation plans.",
            capabilities=CapabilityFlags(supports_cpu=True, supports_parallel_execution=True),
        )
        super().__init__(metadata=metadata or default_meta, container=container, event_bus=event_bus)

    def validate_input(self, input_data: Any) -> InvestigationRequest:
        """Validate and parse input payload into InvestigationRequest."""
        if isinstance(input_data, InvestigationRequest):
            return input_data
        elif isinstance(input_data, dict):
            return InvestigationRequest(**input_data)
        elif isinstance(input_data, str):
            return InvestigationRequest(operator_query=input_data)
        else:
            raise ValidationError(f"PlannerAgent expects InvestigationRequest, dict, or str, got {type(input_data)}")

    def validate_output(self, output_data: Any) -> InvestigationPlan:
        """Validate output payload is an InvestigationPlan."""
        if isinstance(output_data, InvestigationPlan):
            return output_data
        raise ValidationError(f"PlannerAgent output must be an InvestigationPlan, got {type(output_data)}")

    def _execute_internal(
        self, input_data: InvestigationRequest, context: Optional[ExecutionContext] = None
    ) -> InvestigationPlan:
        """
        Decompose investigation request into a structured multi-stage execution plan.
        """
        query = input_data.operator_query.lower()
        complexity = self._classify_complexity(query, input_data)
        target_confidence = self._determine_target_confidence(complexity)
        cost = self._estimate_cost(complexity)

        builder = InvestigationPlanBuilder(input_data)
        builder.set_complexity(complexity)
        builder.set_target_confidence(target_confidence)
        builder.set_estimated_cost(cost)

        # Build stages based on query complexity and intent
        if complexity == ComplexityLevel.SIMPLE:
            # Telemetry & Topology check only
            builder.add_stage(
                name="Telemetry & Topology Assessment",
                agent_plans=[
                    AgentExecutionPlan(agent_name="TelemetryAgent", depends_on=[], mandatory=True),
                    AgentExecutionPlan(agent_name="TopologyAgent", depends_on=[], mandatory=False),
                ],
                parallel_execution=True,
            )
            builder.add_evidence_requirement(
                description="Raw telemetry metrics sample",
                required_agent="TelemetryAgent",
                evidence_type="telemetry",
            )

        elif complexity == ComplexityLevel.MODERATE:
            # Telemetry/Topology -> Prediction -> Incident
            builder.add_stage(
                name="Data Acquisition",
                agent_plans=[
                    AgentExecutionPlan(agent_name="TelemetryAgent", depends_on=[], mandatory=True),
                    AgentExecutionPlan(agent_name="TopologyAgent", depends_on=[], mandatory=False),
                ],
                parallel_execution=True,
            )
            builder.add_stage(
                name="Risk Evaluation & Detection",
                agent_plans=[
                    AgentExecutionPlan(agent_name="PredictionAgent", depends_on=["TelemetryAgent"], mandatory=True),
                    AgentExecutionPlan(agent_name="IncidentAgent", depends_on=["PredictionAgent"], mandatory=True),
                ],
                parallel_execution=False,
            )
            builder.add_evidence_requirement(
                description="Predictive risk assessment score",
                required_agent="PredictionAgent",
                evidence_type="prediction",
            )
            builder.add_evidence_requirement(
                description="Incident anomaly ticket",
                required_agent="IncidentAgent",
                evidence_type="incident",
            )

        else:
            # COMPLEX or CRITICAL: Full 6-agent pipeline
            builder.add_stage(
                name="Telemetry & Topology Ingestion",
                agent_plans=[
                    AgentExecutionPlan(agent_name="TelemetryAgent", depends_on=[], mandatory=True),
                    AgentExecutionPlan(agent_name="TopologyAgent", depends_on=[], mandatory=False),
                ],
                parallel_execution=True,
            )
            builder.add_stage(
                name="Predictive Failure & Incident Management",
                agent_plans=[
                    AgentExecutionPlan(agent_name="PredictionAgent", depends_on=["TelemetryAgent"], mandatory=True),
                    AgentExecutionPlan(agent_name="IncidentAgent", depends_on=["PredictionAgent"], mandatory=True),
                ],
                parallel_execution=False,
            )
            builder.add_stage(
                name="Remediation Planning & RAG Knowledge Synthesis",
                agent_plans=[
                    AgentExecutionPlan(agent_name="RecommendationAgent", depends_on=["IncidentAgent"], mandatory=True),
                    AgentExecutionPlan(
                        agent_name="KnowledgeAgent",
                        depends_on=["RecommendationAgent", "TopologyAgent"],
                        mandatory=False,
                    ),
                ],
                parallel_execution=False,
            )

            # Evidence requirements
            builder.add_evidence_requirement(
                description="Telemetry metrics", required_agent="TelemetryAgent", evidence_type="telemetry"
            )
            builder.add_evidence_requirement(
                description="Risk prediction", required_agent="PredictionAgent", evidence_type="prediction"
            )
            builder.add_evidence_requirement(
                description="Incident ticket", required_agent="IncidentAgent", evidence_type="incident"
            )
            builder.add_evidence_requirement(
                description="Actionable recommendation", required_agent="RecommendationAgent", evidence_type="recommendation"
            )
            builder.add_evidence_requirement(
                description="RAG runbook knowledge", required_agent="KnowledgeAgent", evidence_type="knowledge", is_mandatory=False
            )

        builder.add_metadata("classified_by", self.name)
        builder.add_metadata("query_raw", input_data.operator_query)

        plan = builder.build()
        self._logger.info(
            f"PlannerAgent generated plan '{plan.plan_id}' ({complexity.value}, "
            f"stages={len(plan.stages)}, target_confidence={target_confidence:.2f})"
        )
        return plan

    def _classify_complexity(self, query: str, request: InvestigationRequest) -> ComplexityLevel:
        """Classify operator query complexity using heuristic rule matching."""
        if any(w in query for w in ["critical", "outage", "down", "emergency", "crash", "failure"]):
            return ComplexityLevel.CRITICAL
        if any(w in query for w in ["unstable", "why", "root cause", "investigate", "remediation", "runbook"]):
            return ComplexityLevel.COMPLEX
        if any(w in query for w in ["predict", "risk", "latency", "loss", "flapping", "health"]):
            return ComplexityLevel.MODERATE
        return ComplexityLevel.SIMPLE

    def _determine_target_confidence(self, complexity: ComplexityLevel) -> float:
        """Determine target confidence threshold based on complexity."""
        if complexity == ComplexityLevel.CRITICAL:
            return 0.95
        elif complexity == ComplexityLevel.COMPLEX:
            return 0.85
        elif complexity == ComplexityLevel.MODERATE:
            return 0.80
        return 0.70

    def _estimate_cost(self, complexity: ComplexityLevel) -> float:
        """Estimate relative compute cost units."""
        cost_map = {
            ComplexityLevel.SIMPLE: 1.0,
            ComplexityLevel.MODERATE: 2.5,
            ComplexityLevel.COMPLEX: 5.0,
            ComplexityLevel.CRITICAL: 10.0,
        }
        return cost_map.get(complexity, 2.5)
