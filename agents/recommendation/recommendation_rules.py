"""
Recommendation Rules Engine Module.

Centralizes business rules mapping incident severity to recommendation priority,
building dynamic execution plans, formatting CLI commands, and constructing rollback plans.
"""

from typing import Any, Dict, List

from agents.incident.incident_models import IncidentRecord, IncidentSeverity
from agents.recommendation.recommendation_models import (
    ExecutionPlan,
    ImpactAssessment,
    RecommendationAction,
    RecommendationCommand,
    RecommendationPriority,
    RiskLevel,
    RollbackPlan,
)
from agents.recommendation.recommendation_templates import RecommendationTemplateRegistry


class RecommendationRules:
    """
    Centralized rules engine for transforming incidents into structured remediation plans.
    """

    @staticmethod
    def map_severity_to_priority(severity: IncidentSeverity) -> RecommendationPriority:
        """
        Map IncidentSeverity to RecommendationPriority.

        Args:
            severity: IncidentSeverity enum.

        Returns:
            RecommendationPriority enum.
        """
        if severity == IncidentSeverity.CRITICAL:
            return RecommendationPriority.CRITICAL
        if severity == IncidentSeverity.HIGH:
            return RecommendationPriority.HIGH
        if severity == IncidentSeverity.MEDIUM:
            return RecommendationPriority.MEDIUM
        return RecommendationPriority.LOW

    @classmethod
    def build_execution_plan(cls, template: Dict[str, Any], interface: str) -> ExecutionPlan:
        """
        Construct strongly typed ExecutionPlan from template with formatted CLI commands.

        Args:
            template: Remediation template dictionary.
            interface: Target interface name.

        Returns:
            ExecutionPlan instance.
        """
        raw_actions = template.get("actions", [])
        actions: List[RecommendationAction] = []

        for item in raw_actions:
            cli_cmds: List[RecommendationCommand] = []
            for cmd in item.get("cli_commands", []):
                fmt_text = cmd["command_text"].format(interface=interface)
                cli_cmds.append(
                    RecommendationCommand(
                        command_text=fmt_text,
                        description=cmd["description"],
                        target_device=interface,
                        platform=cmd.get("platform", "cisco_ios"),
                        is_reversable=cmd.get("is_reversable", True),
                    )
                )

            ver_cmds: List[RecommendationCommand] = []
            for cmd in item.get("verification_commands", []):
                fmt_text = cmd["command_text"].format(interface=interface)
                ver_cmds.append(
                    RecommendationCommand(
                        command_text=fmt_text,
                        description=cmd["description"],
                        target_device=interface,
                        platform=cmd.get("platform", "cisco_ios"),
                        is_reversable=cmd.get("is_reversable", True),
                    )
                )

            actions.append(
                RecommendationAction(
                    title=item["title"],
                    description=item["description"],
                    sequence_order=item.get("sequence_order", 1),
                    cli_commands=cli_cmds,
                    verification_commands=ver_cmds,
                )
            )

        return ExecutionPlan(
            actions=actions,
            estimated_duration_min=float(template.get("estimated_duration_min", 5.0)),
            automation_possible=bool(template.get("automation_possible", True)),
        )

    @classmethod
    def build_rollback_plan(cls, template: Dict[str, Any], interface: str) -> RollbackPlan:
        """
        Construct RollbackPlan from template with formatted commands.

        Args:
            template: Remediation template dictionary.
            interface: Target interface name.

        Returns:
            RollbackPlan instance.
        """
        raw_rb = template.get("rollback_plan", {})
        rb_cmds: List[RecommendationCommand] = []

        for cmd in raw_rb.get("rollback_commands", []):
            fmt_text = cmd["command_text"].format(interface=interface)
            rb_cmds.append(
                RecommendationCommand(
                    command_text=fmt_text,
                    description=cmd["description"],
                    target_device=interface,
                    platform=cmd.get("platform", "cisco_ios"),
                    is_reversable=cmd.get("is_reversable", True),
                )
            )

        return RollbackPlan(
            steps=list(raw_rb.get("steps", [])),
            rollback_commands=rb_cmds,
            estimated_rollback_duration_min=float(raw_rb.get("estimated_rollback_duration_min", 2.0)),
        )

    @classmethod
    def build_impact_assessment(cls, template: Dict[str, Any], incident: IncidentRecord) -> ImpactAssessment:
        """
        Construct ImpactAssessment from template and incident details.

        Args:
            template: Remediation template dictionary.
            incident: Target IncidentRecord.

        Returns:
            ImpactAssessment instance.
        """
        raw_impact = template.get("impact_assessment", {})
        return ImpactAssessment(
            business_impact=raw_impact.get("business_impact", "MODERATE_BUSINESS_IMPACT"),
            affected_services=list(raw_impact.get("affected_services", [])),
            risk_level=RiskLevel(raw_impact.get("risk_level", RiskLevel.LOW)),
            downtime_expected=bool(raw_impact.get("downtime_expected", False)),
        )
