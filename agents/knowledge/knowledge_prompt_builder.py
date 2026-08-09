"""
Knowledge Prompt Builder Module.

Constructs structured, contextual prompts combining Incident, Recommendation,
Topology, Runbooks, and Documentation context. Pure formatting layer — zero LLM code.
"""

from typing import Any, Dict, List, Optional


class KnowledgePromptBuilder:
    """
    Builder for assembling structured AI prompts for the Knowledge Subsystem.
    """

    @staticmethod
    def build_prompt(
        incident_data: Dict[str, Any],
        recommendation_data: Dict[str, Any],
        topology_data: Optional[Dict[str, Any]] = None,
        runbooks: Optional[List[Dict[str, Any]]] = None,
        topology_analysis: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Assemble a single structured text prompt string.

        Args:
            incident_data: Incident payload dict.
            recommendation_data: Recommendation payload dict.
            topology_data: Optional basic topology context dict (device registry entry).
            runbooks: Optional list of runbook document dicts.
            topology_analysis: Optional TopologyAnalysis.model_dump(mode='json')
                               produced by the TopologyAgent.  When present, a
                               rich TOPOLOGY INTELLIGENCE section is injected into
                               the prompt so that the LLM can reason about network
                               graph context (blast radius, SPOFs, dependencies).

        Returns:
            Formatted prompt text string.
        """
        inc_id = incident_data.get("incident_id", "N/A")
        inc_title = incident_data.get("title", "Network Anomaly")
        severity = incident_data.get("severity", "MEDIUM")
        risk_score = incident_data.get("risk_score", 0.0)
        signals = incident_data.get("contributing_signals", [])

        rec_id = recommendation_data.get("recommendation_id", "N/A")
        summary = recommendation_data.get("summary", "")
        priority = recommendation_data.get("priority", "MEDIUM")
        actions = recommendation_data.get("recommended_actions", [])

        exec_plan = recommendation_data.get("execution_plan", {})
        plan_actions = exec_plan.get("actions", []) if isinstance(exec_plan, dict) else []

        top_info = ""
        if topology_data:
            top_info = (
                f"\n--- TOPOLOGY CONTEXT ---\n"
                f"Device: {topology_data.get('name', 'N/A')} [{topology_data.get('type', 'Unknown')}]\n"
                f"Location: {topology_data.get('location', 'Unknown')}\n"
            )

        # Rich topology intelligence section from TopologyAgent
        topology_intelligence = ""
        if topology_analysis:
            topology_intelligence = KnowledgePromptBuilder.build_topology_section(
                topology_analysis
            )

        runbook_info = ""
        if runbooks:
            runbook_info = "\n--- REFERENCE RUNBOOKS & KNOWLEDGE ---\n"
            for rb in runbooks:
                runbook_info += f"• [{rb.get('source', 'Doc')}] {rb.get('chunk', '')}\n"

        prompt = (
            f"You are NOC Copilot AI, an enterprise Network Operations Center AI Specialist.\n"
            f"Analyze the following operational incident and remediation plan to provide a root cause analysis and action summary.\n\n"
            f"--- INCIDENT DETAILS ---\n"
            f"Incident ID: {inc_id}\n"
            f"Title: {inc_title}\n"
            f"Severity: {severity}\n"
            f"Risk Score: {risk_score:.2f}\n"
            f"Contributing Signals: {', '.join(signals) if signals else 'None'}\n"
            f"{top_info}"
            f"{topology_intelligence}\n"
            f"--- RECOMMENDED REMEDIATION PLAN ---\n"
            f"Recommendation ID: {rec_id}\n"
            f"Priority: {priority}\n"
            f"Summary: {summary}\n"
            f"Key Actions: {', '.join(actions) if actions else 'None'}\n"
            f"Configured Action Steps Count: {len(plan_actions)}\n"
            f"{runbook_info}\n"
            f"Please generate a structured analysis containing:\n"
            f"1. ROOT CAUSE ANALYSIS\n"
            f"2. RECOMMENDED ACTIONS\n"
            f"3. CONFIDENCE SCORE"
        )

        return prompt

    @staticmethod
    def build_topology_section(topology_analysis: Dict[str, Any]) -> str:
        """
        Render a rich TOPOLOGY INTELLIGENCE section from a TopologyAnalysis dict.

        This section is included in the LLM prompt when a TopologyAnalysis has
        been computed by the TopologyAgent, providing the model with network
        graph context to produce more accurate root-cause analysis.

        Args:
            topology_analysis: TopologyAnalysis.model_dump(mode='json') dict.

        Returns:
            Formatted multi-line string section for prompt injection.
        """
        device_id: str = topology_analysis.get("device_id", "N/A")
        interface: str = topology_analysis.get("interface", "")
        overall_severity: str = topology_analysis.get("overall_severity", "NONE")
        routing_summary: str = topology_analysis.get("routing_summary", "")
        upstream: List[str] = topology_analysis.get("upstream_devices", [])
        downstream: List[str] = topology_analysis.get("downstream_devices", [])
        impacted: List[str] = topology_analysis.get("impacted_devices", [])

        # Blast-radius sub-dict
        br: Dict[str, Any] = topology_analysis.get("blast_radius") or {}
        total_affected: int = br.get("total_affected_nodes", 0)
        impact_pct: float = br.get("impact_percentage", 0.0)
        spofs: List[str] = br.get("single_points_of_failure", [])
        affected_svcs: List[str] = br.get("affected_services", [])

        # Service impacts list
        svc_impacts: List[Dict[str, Any]] = topology_analysis.get("impacted_services", [])
        critical_svcs = [
            s.get("service_name", "")
            for s in svc_impacts
            if s.get("severity") in ("CRITICAL", "HIGH")
        ]

        lines: List[str] = [
            "\n--- TOPOLOGY INTELLIGENCE (Graph Analysis) ---",
            f"Affected Device   : {device_id}"
            + (f" (interface: {interface})" if interface else ""),
            f"Graph Severity    : {overall_severity}",
            f"Blast Radius      : {total_affected} node(s) affected"
            f" ({impact_pct:.1f}% of network)",
            f"Upstream Devices  : {', '.join(upstream) if upstream else 'None'}",
            f"Downstream Devices: {', '.join(downstream) if downstream else 'None'}",
            f"Impacted Devices  : {', '.join(impacted) if impacted else 'None'}",
            f"Affected Services : {', '.join(affected_svcs) if affected_svcs else 'None'}",
            f"Critical/High Svcs: {', '.join(critical_svcs) if critical_svcs else 'None'}",
            f"SPOFs Exposed     : {', '.join(spofs) if spofs else 'None'}",
        ]

        if routing_summary:
            lines.append(f"Routing Summary   :\n{routing_summary}")

        return "\n".join(lines) + "\n"
