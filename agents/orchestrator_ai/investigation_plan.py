"""
Investigation Plan Builder and Helper Utilities.

Provides fluent builder interfaces and validation methods for constructing and
inspecting strongly-typed InvestigationPlan instances.
"""

from typing import Any, Dict, List, Optional
import uuid

from agents.core.exceptions import ValidationError
from agents.orchestrator_ai.investigation_models import (
    AgentExecutionPlan,
    ComplexityLevel,
    EvidenceRequirement,
    InvestigationPlan,
    InvestigationRequest,
    InvestigationStage,
)


class InvestigationPlanBuilder:
    """
    Fluent Builder for constructing InvestigationPlan instances cleanly.
    """

    def __init__(self, request: InvestigationRequest) -> None:
        self._request_id = request.request_id
        self._classification = ComplexityLevel.MODERATE
        self._estimated_cost = 1.0
        self._target_confidence = 0.85
        self._stages: List[InvestigationStage] = []
        self._required_agents: List[str] = []
        self._required_evidence: List[EvidenceRequirement] = []
        self._metadata: Dict[str, Any] = {}

    def set_complexity(self, complexity: ComplexityLevel) -> "InvestigationPlanBuilder":
        """Set query complexity classification."""
        self._classification = complexity
        return self

    def set_estimated_cost(self, cost: float) -> "InvestigationPlanBuilder":
        """Set total estimated cost unit."""
        self._estimated_cost = max(0.0, cost)
        return self

    def set_target_confidence(self, confidence: float) -> "InvestigationPlanBuilder":
        """Set target confidence threshold (0.0 to 1.0)."""
        self._target_confidence = max(0.0, min(1.0, confidence))
        return self

    def add_stage(
        self,
        name: str,
        agent_plans: List[AgentExecutionPlan],
        parallel_execution: bool = True,
        stop_on_failure: bool = False,
    ) -> "InvestigationPlanBuilder":
        """Add an execution stage containing agent execution plans."""
        stage = InvestigationStage(
            stage_id=str(uuid.uuid4()),
            name=name,
            agent_plans=agent_plans,
            parallel_execution=parallel_execution,
            stop_on_failure=stop_on_failure,
        )
        self._stages.append(stage)
        for ap in agent_plans:
            if ap.agent_name not in self._required_agents:
                self._required_agents.append(ap.agent_name)
        return self

    def add_evidence_requirement(
        self,
        description: str,
        required_agent: str,
        evidence_type: str,
        is_mandatory: bool = True,
    ) -> "InvestigationPlanBuilder":
        """Add an evidence requirement entry."""
        req = EvidenceRequirement(
            requirement_id=str(uuid.uuid4()),
            description=description,
            required_agent=required_agent,
            evidence_type=evidence_type,
            is_mandatory=is_mandatory,
        )
        self._required_evidence.append(req)
        return self

    def add_metadata(self, key: str, value: Any) -> "InvestigationPlanBuilder":
        """Attach arbitrary metadata entry."""
        self._metadata[key] = value
        return self

    def build(self) -> InvestigationPlan:
        """
        Validate and return the constructed InvestigationPlan instance.
        """
        if not self._stages:
            raise ValidationError("InvestigationPlan must contain at least one stage.")

        plan = InvestigationPlan(
            plan_id=str(uuid.uuid4()),
            request_id=self._request_id,
            query_classification=self._classification,
            estimated_cost=self._estimated_cost,
            target_confidence=self._target_confidence,
            stages=self._stages,
            required_agents=self._required_agents,
            required_evidence=self._required_evidence,
            metadata=self._metadata,
        )
        return plan
