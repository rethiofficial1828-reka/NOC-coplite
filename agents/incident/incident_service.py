"""
Incident Service Module.

Business logic service for incident processing, deduplication, severity mapping,
auto-resolution triggers, state machine transitions, and repository persistence.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from agents.core.logger import get_agent_logger
from agents.incident.incident_models import (
    IncidentAssignment,
    IncidentRecord,
    IncidentSeverity,
    IncidentStatistics,
    IncidentStatus,
    IncidentTimeline,
)
from agents.incident.incident_repository import IncidentRepository
from agents.incident.incident_rules import IncidentRules
from agents.incident.incident_state_machine import IncidentStateMachine
from agents.incident.incident_validator import IncidentValidator
from agents.schemas.schemas import PredictionResult

logger = get_agent_logger("IncidentService")


class IncidentService:
    """
    Business service layer managing incident evaluation, deduplication, and lifecycle transitions.
    """

    def __init__(
        self,
        repository: Optional[IncidentRepository] = None,
        validator: Optional[IncidentValidator] = None,
        rules: Optional[IncidentRules] = None,
    ) -> None:
        """
        Initialize IncidentService.

        Args:
            repository: IncidentRepository instance.
            validator: IncidentValidator instance.
            rules: IncidentRules instance.
        """
        self._repository = repository or IncidentRepository()
        self._validator = validator or IncidentValidator()
        self._rules = rules or IncidentRules()

    @property
    def repository(self) -> IncidentRepository:
        """Repository instance."""
        return self._repository

    def process_prediction(
        self, prediction_data: Union[PredictionResult, Dict[str, Any]]
    ) -> Tuple[Optional[IncidentRecord], str]:
        """
        Process a prediction payload, evaluating deduplication, severity, and auto-resolution rules.

        Args:
            prediction_data: PredictionResult object or raw dictionary payload.

        Returns:
            Tuple of (IncidentRecord or None, action_tag string e.g. "created", "updated", "severity_changed", "resolved", "ignored").
        """
        if isinstance(prediction_data, PredictionResult):
            raw = prediction_data.model_dump(mode="json")
        else:
            raw = dict(prediction_data)

        self._validator.validate_prediction_payload(raw)

        interface = str(raw.get("interface") or raw.get("device_id"))
        risk_score = float(raw["risk_score"])
        time_to_impact = float(raw.get("time_to_impact", -1.0))
        signals = list(raw.get("contributing_signals", []))

        incident_type = self._rules.determine_incident_type(signals)
        new_severity = self._rules.map_risk_to_severity(risk_score)

        # Check deduplication: search for existing active incident
        active_incident = self._repository.find_active_incident(interface, incident_type) or self._repository.find_active_incident(interface)

        if active_incident:
            # Check auto-resolution rule
            if self._rules.should_auto_resolve(risk_score, active_incident.status):
                updated_inc = IncidentStateMachine.transition(
                    active_incident,
                    IncidentStatus.RESOLVED,
                    reason=f"Auto-resolved: risk score recovered to {risk_score:.2f}",
                )
                self._repository.update_incident(updated_inc)
                logger.info(f"Auto-resolved incident '{updated_inc.incident_id}' for '{interface}'.")
                return updated_inc, "resolved"

            # Active incident exists: update fields and check severity change
            action_tag = "updated"
            if active_incident.severity != new_severity:
                old_sev = active_incident.severity
                active_incident.severity = new_severity
                action_tag = "severity_changed"

                timeline_evt = IncidentTimeline(
                    incident_id=active_incident.incident_id,
                    event_type="SEVERITY_CHANGED",
                    description=f"Severity escalated/de-escalated from '{old_sev.value}' to '{new_severity.value}'",
                    metadata={"old_severity": old_sev.value, "new_severity": new_severity.value, "risk_score": risk_score},
                )
                active_incident.timeline.append(timeline_evt)

            active_incident.risk_score = risk_score
            active_incident.time_to_impact = time_to_impact
            active_incident.contributing_signals = signals
            active_incident.updated_at = datetime.now(timezone.utc)

            # Append update timeline event
            update_evt = IncidentTimeline(
                incident_id=active_incident.incident_id,
                event_type="PREDICTION_UPDATED",
                description=f"Prediction updated: risk_score={risk_score:.2f}, time_to_impact={time_to_impact:.1f}m",
                metadata={"risk_score": risk_score, "time_to_impact": time_to_impact},
            )
            active_incident.timeline.append(update_evt)

            self._repository.update_incident(active_incident)
            return active_incident, action_tag

        else:
            # No active incident exists: check if risk score warrants creation
            if self._rules.should_create_incident(risk_score):
                inc_id = self._repository.generate_next_id()
                title = self._rules.generate_incident_title(interface, incident_type, new_severity)
                now = datetime.now(timezone.utc)

                initial_timeline = IncidentTimeline(
                    incident_id=inc_id,
                    event_type="CREATED",
                    description=f"Incident created automatically by IncidentAgent (risk_score={risk_score:.2f})",
                    timestamp=now,
                    author="IncidentAgent",
                    metadata={"risk_score": risk_score, "signals": signals},
                )

                new_incident = IncidentRecord(
                    incident_id=inc_id,
                    device_id=interface,
                    interface=interface,
                    incident_type=incident_type,
                    title=title,
                    description=f"Automated predictive incident detected on {interface}.",
                    severity=new_severity,
                    status=IncidentStatus.OPEN,
                    risk_score=risk_score,
                    time_to_impact=time_to_impact,
                    contributing_signals=signals,
                    assignment=IncidentAssignment(),
                    timeline=[initial_timeline],
                    created_at=now,
                    updated_at=now,
                )

                self._validator.validate_incident_record(new_incident)
                self._repository.create_incident(new_incident)
                logger.info(f"Created new incident '{inc_id}' ({new_severity.value}) for '{interface}'.")
                return new_incident, "created"

            return None, "ignored"

    def get_incident(self, incident_id: str) -> Optional[IncidentRecord]:
        """Fetch incident by ID."""
        return self._repository.get_incident(incident_id)

    def transition_incident_status(
        self, incident_id: str, target_status: IncidentStatus, reason: str = "", author: str = "User"
    ) -> IncidentRecord:
        """
        Transition status of an existing incident via IncidentStateMachine.

        Args:
            incident_id: Incident ID.
            target_status: Target status enum.
            reason: Reason string.
            author: Author string.

        Returns:
            Updated IncidentRecord.
        """
        inc = self._repository.get_incident(incident_id)
        if not inc:
            raise KeyError(f"Incident with ID '{incident_id}' not found.")

        updated_inc = IncidentStateMachine.transition(inc, target_status, reason=reason, author=author)
        return self._repository.update_incident(updated_inc)

    def get_statistics(self) -> IncidentStatistics:
        """Retrieve aggregated incident statistics."""
        return self._repository.get_statistics()
