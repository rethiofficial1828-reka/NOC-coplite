"""
Recommendation Service Module.

Business logic service for transforming IncidentRecords into structured remediation plans,
populating CLI execution and rollback commands, applying templates, and persisting recommendations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from agents.core.logger import get_agent_logger
from agents.incident.incident_models import IncidentRecord, IncidentSeverity
from agents.recommendation.recommendation_models import RecommendationRecord
from agents.recommendation.recommendation_repository import RecommendationRepository
from agents.recommendation.recommendation_rules import RecommendationRules
from agents.recommendation.recommendation_templates import RecommendationTemplateRegistry
from agents.recommendation.recommendation_validator import RecommendationValidator

logger = get_agent_logger("RecommendationService")


class RecommendationService:
    """
    Business service layer managing recommendation generation, CLI command formatting, and persistence.
    """

    def __init__(
        self,
        repository: Optional[RecommendationRepository] = None,
        validator: Optional[RecommendationValidator] = None,
        rules: Optional[RecommendationRules] = None,
    ) -> None:
        """
        Initialize RecommendationService.

        Args:
            repository: RecommendationRepository instance.
            validator: RecommendationValidator instance.
            rules: RecommendationRules instance.
        """
        self._repository = repository or RecommendationRepository()
        self._validator = validator or RecommendationValidator()
        self._rules = rules or RecommendationRules()

    @property
    def repository(self) -> RecommendationRepository:
        """Repository instance."""
        return self._repository

    def generate_recommendation_for_incident(
        self, incident_data: Union[IncidentRecord, Dict[str, Any]]
    ) -> RecommendationRecord:
        """
        Generate or update a RecommendationRecord from an IncidentRecord or incident payload dictionary.

        Args:
            incident_data: IncidentRecord or dictionary payload.

        Returns:
            Generated and saved RecommendationRecord object.
        """
        if isinstance(incident_data, IncidentRecord):
            inc_dict = incident_data.model_dump(mode="json")
            severity = incident_data.severity
        else:
            inc_dict = dict(incident_data)
            self._validator.validate_incident_payload(inc_dict)
            sev_val = inc_dict.get("severity", "MEDIUM")
            severity = IncidentSeverity(sev_val) if isinstance(sev_val, str) else IncidentSeverity.MEDIUM

        inc_id = str(inc_dict["incident_id"])
        device_id = str(inc_dict.get("device_id") or inc_dict.get("interface"))
        interface = str(inc_dict.get("interface") or device_id)
        inc_type = str(inc_dict.get("incident_type", "PREDICTIVE_FAULT_RISK"))

        template = RecommendationTemplateRegistry.get_template(inc_type)
        priority = self._rules.map_severity_to_priority(severity)

        exec_plan = self._rules.build_execution_plan(template, interface)
        rollback_plan = self._rules.build_rollback_plan(template, interface)
        dummy_inc = IncidentRecord(
            incident_id=inc_id, device_id=device_id, interface=interface, title=inc_dict.get("title", "Incident"), severity=severity
        )
        impact = self._rules.build_impact_assessment(template, dummy_inc)

        existing_list = self._repository.find_by_incident(inc_id)
        now = datetime.now(timezone.utc)

        if existing_list:
            rec = existing_list[0]
            rec.summary = template["summary"]
            rec.priority = priority
            rec.root_cause_hypothesis = template["root_cause_hypothesis"]
            rec.recommended_actions = list(template["recommended_actions"])
            rec.execution_plan = exec_plan
            rec.rollback_plan = rollback_plan
            rec.impact_assessment = impact
            rec.cited_sources = list(template.get("cited_sources", []))
            rec.updated_at = now

            self._validator.validate_recommendation_record(rec)
            self._repository.update_recommendation(rec)
            logger.info(f"Updated existing recommendation '{rec.recommendation_id}' for incident '{inc_id}'.")
            return rec

        else:
            rec_id = self._repository.generate_next_id()
            rec = RecommendationRecord(
                recommendation_id=rec_id,
                incident_id=inc_id,
                device_id=device_id,
                interface=interface,
                summary=template["summary"],
                priority=priority,
                root_cause_hypothesis=template["root_cause_hypothesis"],
                recommended_actions=list(template["recommended_actions"]),
                execution_plan=exec_plan,
                rollback_plan=rollback_plan,
                impact_assessment=impact,
                cited_sources=list(template.get("cited_sources", [])),
                created_at=now,
                updated_at=now,
            )

            self._validator.validate_recommendation_record(rec)
            self._repository.create_recommendation(rec)
            logger.info(f"Created new recommendation '{rec_id}' for incident '{inc_id}'.")
            return rec

    def get_recommendations_for_incident(self, incident_id: str) -> List[RecommendationRecord]:
        """Fetch recommendations for an incident ID."""
        return self._repository.find_by_incident(incident_id)

    def get_recommendations_for_device(self, device_id_or_interface: str) -> List[RecommendationRecord]:
        """Fetch recommendations for a device or interface."""
        return self._repository.find_by_device(device_id_or_interface)
