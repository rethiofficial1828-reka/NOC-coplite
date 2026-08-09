"""
Incident Business Rules Engine Module.

Centralizes all business logic rules for severity mapping, incident classification,
auto-resolution triggers, escalation logic, and business impact estimation.
"""

from typing import List

from agents.incident.incident_models import IncidentSeverity, IncidentStatus


class IncidentRules:
    """
    Centralized business rules engine for incident evaluation.
    """

    @staticmethod
    def map_risk_to_severity(risk_score: float) -> IncidentSeverity:
        """
        Map a continuous predictive risk score (0.0 to 1.0) to an IncidentSeverity level.

        Args:
            risk_score: Float risk score between 0.0 and 1.0.

        Returns:
            IncidentSeverity enum value.
        """
        score = float(max(0.0, min(1.0, risk_score)))
        if score >= 0.85:
            return IncidentSeverity.CRITICAL
        if score >= 0.70:
            return IncidentSeverity.HIGH
        if score >= 0.45:
            return IncidentSeverity.MEDIUM
        if score >= 0.25:
            return IncidentSeverity.LOW
        return IncidentSeverity.INFO

    @staticmethod
    def determine_incident_type(contributing_signals: List[str]) -> str:
        """
        Infer categorical incident type based on contributing signal keywords.

        Args:
            contributing_signals: List of signal strings.

        Returns:
            Categorical incident type string.
        """
        signals_text = " ".join([s.lower() for s in contributing_signals])

        if "drop" in signals_text:
            return "EGRESS_PACKET_DROPS"
        if "routing" in signals_text or "flap" in signals_text:
            return "ROUTING_INSTABILITY"
        if "latency" in signals_text:
            return "LATENCY_SPIKE"
        if "utilization" in signals_text or "congestion" in signals_text:
            return "NETWORK_CONGESTION"

        return "PREDICTIVE_FAULT_RISK"

    @staticmethod
    def should_create_incident(risk_score: float) -> bool:
        """
        Determine if risk score warrants creating a new incident.

        Args:
            risk_score: Float risk score.

        Returns:
            True if risk_score >= 0.25, False otherwise.
        """
        return risk_score >= 0.25

    @staticmethod
    def should_auto_resolve(risk_score: float, status: IncidentStatus) -> bool:
        """
        Determine if an active incident should be automatically resolved due to risk recovery.

        Args:
            risk_score: Float risk score.
            status: Current IncidentStatus.

        Returns:
            True if risk_score < 0.20 and incident status is active.
        """
        active_statuses = {
            IncidentStatus.NEW,
            IncidentStatus.OPEN,
            IncidentStatus.ACKNOWLEDGED,
            IncidentStatus.IN_PROGRESS,
            IncidentStatus.MITIGATED,
        }
        return risk_score < 0.20 and status in active_statuses

    @staticmethod
    def calculate_business_impact(severity: IncidentSeverity, device_type: str = "") -> str:
        """
        Calculate qualitative business impact level based on severity and device criticality.

        Args:
            severity: IncidentSeverity level.
            device_type: Monitored device type (e.g. 'Core Switch', 'WAN Interface').

        Returns:
            Business impact classification string.
        """
        is_core = "core" in device_type.lower() or "wan" in device_type.lower()

        if severity == IncidentSeverity.CRITICAL or (severity == IncidentSeverity.HIGH and is_core):
            return "CRITICAL_BUSINESS_IMPACT"
        if severity == IncidentSeverity.HIGH or (severity == IncidentSeverity.MEDIUM and is_core):
            return "HIGH_BUSINESS_IMPACT"
        if severity == IncidentSeverity.MEDIUM:
            return "MODERATE_BUSINESS_IMPACT"
        return "LOW_BUSINESS_IMPACT"

    @staticmethod
    def generate_incident_title(interface: str, incident_type: str, severity: IncidentSeverity) -> str:
        """
        Generate short human-readable title for incident record.

        Args:
            interface: Interface or device name.
            incident_type: Incident category.
            severity: IncidentSeverity level.

        Returns:
            Formatted title string.
        """
        readable_type = incident_type.replace("_", " ").title()
        return f"[{severity.value}] {readable_type} on {interface}"
