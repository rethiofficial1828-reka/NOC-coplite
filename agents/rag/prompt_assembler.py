"""
Prompt Assembler Module.

Implements PromptAssembler for token-budgeted, structured enterprise prompt construction.
Assembles CAG operational state, retrieved knowledge chunks, and evidence citations into a final prompt package.
"""

from typing import List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.citations import CitationGenerator
from agents.rag.interfaces import IPromptAssembler
from agents.rag.models import (
    CAGContext,
    Citation,
    ContextQuality,
    PromptPackage,
    RetrievalResult,
)

logger = get_agent_logger("PromptAssembler")


class PromptAssembler(IPromptAssembler):
    """
    Enterprise Prompt Assembler with token budget management and context compression.
    """

    DEFAULT_SYSTEM_INSTRUCTION = (
        "You are NOC Copilot AI, an enterprise Network Operations Center AI Specialist.\n"
        "Analyze the operational network state, active incidents, graph topology, and retrieved evidence.\n"
        "Provide a clear, evidence-based root cause analysis, action summary, and confidence score.\n"
        "Cite specific evidence sources where appropriate."
    )

    def assemble_prompt(
        self,
        cag_context: CAGContext,
        retrieved_results: List[RetrievalResult],
        quality: Optional[ContextQuality] = None,
        max_tokens: int = 2048,
    ) -> PromptPackage:
        """
        Assemble structured LLM prompt string with token budgeting and citations.

        Args:
            cag_context: Unified CAGContext model.
            retrieved_results: Ranked candidate retrieval results.
            quality: Optional ContextQuality evaluation.
            max_tokens: Target token limit (~4 chars per token).

        Returns:
            PromptPackage model instance.
        """
        max_chars = max_tokens * 4
        was_compressed = False

        # Generate Citations
        citations = CitationGenerator.generate_citations(retrieved_results)
        citations_text = CitationGenerator.format_citations_text(citations)

        # 1. Operator Query
        query_str = cag_context.operator_query or "Perform root cause triage and remediation analysis."

        # 2. Telemetry Section
        tel_text = ""
        if cag_context.telemetry_data:
            tel = cag_context.telemetry_data
            tel_text = (
                f"\n--- TELEMETRY METRICS ---\n"
                f"Device: {tel.get('device_id', cag_context.device_id)} | Interface: {tel.get('interface', cag_context.interface)}\n"
                f"Metrics: {tel.get('metrics', {})}\n"
            )

        # 3. Prediction Section
        pred_text = ""
        if cag_context.prediction_data:
            p = cag_context.prediction_data
            pred_text = (
                f"\n--- RISK PREDICTION ---\n"
                f"Risk Score: {p.get('risk_score', 0.0):.2f} | Time to Impact: {p.get('time_to_impact', -1.0)}m\n"
                f"Contributing Signals: {', '.join(p.get('contributing_signals', []))}\n"
            )

        # 4. Incident Section
        inc_text = ""
        if cag_context.incident_data:
            inc = cag_context.incident_data
            inc_text = (
                f"\n--- ACTIVE INCIDENT ---\n"
                f"Incident ID: {inc.get('incident_id', 'N/A')} | Severity: {inc.get('severity', 'MEDIUM')}\n"
                f"Title: {inc.get('title', 'Network Fault')}\n"
            )

        # 5. Recommendation Section
        rec_text = ""
        if cag_context.recommendation_data:
            rec = cag_context.recommendation_data
            rec_text = (
                f"\n--- REMEDIATION PLAN ---\n"
                f"Recommendation ID: {rec.get('recommendation_id', 'N/A')} | Priority: {rec.get('priority', 'MEDIUM')}\n"
                f"Summary: {rec.get('summary', '')}\n"
                f"Actions: {', '.join(rec.get('recommended_actions', []))}\n"
            )

        # 6. Topology Section
        top_text = ""
        if cag_context.topology_data:
            top = cag_context.topology_data
            br = top.get("blast_radius") or {}
            top_text = (
                f"\n--- TOPOLOGY INTELLIGENCE ---\n"
                f"Graph Severity: {top.get('overall_severity', 'NONE')}\n"
                f"Blast Radius: {br.get('total_affected_nodes', 0)} nodes ({br.get('impact_percentage', 0.0):.1f}%)\n"
                f"Upstream: {', '.join(top.get('upstream_devices', []))}\n"
                f"Downstream: {', '.join(top.get('downstream_devices', []))}\n"
                f"SPOFs: {', '.join(br.get('single_points_of_failure', []))}\n"
            )

        # 7. Retrieved Knowledge Chunks Section
        know_text = ""
        if retrieved_results:
            know_text = "\n--- RETRIEVED ENTERPRISE RUNBOOKS & KNOWLEDGE ---\n"
            for res in retrieved_results[:3]:
                chunk = res.chunk
                know_text += f"• [{chunk.source}] {chunk.content[:250].strip()}\n"

        # Quality warning header if evidence is insufficient
        quality_header = ""
        if quality and not quality.is_sufficient:
            quality_header = (
                f"\n[NOTICE: Context quality score is {quality.quality_score:.2f} ({quality.status.value}). "
                f"If retrieved evidence is inadequate, explicitly state that operational data is insufficient.]\n"
            )

        # Assemble full text
        body = (
            f"{quality_header}\n"
            f"--- OPERATOR QUERY ---\n"
            f"{query_str}\n"
            f"{tel_text}"
            f"{pred_text}"
            f"{inc_text}"
            f"{rec_text}"
            f"{top_text}"
            f"{know_text}\n"
            f"{citations_text}\n\n"
            f"Please generate a structured response containing:\n"
            f"1. ROOT CAUSE ANALYSIS\n"
            f"2. RECOMMENDED ACTIONS\n"
            f"3. CONFIDENCE SCORE"
        )

        full_prompt = f"{self.DEFAULT_SYSTEM_INSTRUCTION}\n\n{body}"

        # Token budget enforcement (compression)
        if len(full_prompt) > max_chars:
            logger.info(f"Prompt character length ({len(full_prompt)}) exceeded budget ({max_chars}). Compressing.")
            body = (
                f"{quality_header}\n"
                f"--- OPERATOR QUERY ---\n"
                f"{query_str}\n"
                f"{inc_text}"
                f"{top_text}"
                f"{know_text[:600]}\n"
                f"{citations_text}\n\n"
                f"1. ROOT CAUSE ANALYSIS\n2. RECOMMENDED ACTIONS\n3. CONFIDENCE SCORE"
            )
            full_prompt = f"{self.DEFAULT_SYSTEM_INSTRUCTION}\n\n{body}"
            was_compressed = True

        est_tokens = max(1, len(full_prompt) // 4)

        logger.info(f"Assembled PromptPackage (~{est_tokens} tokens, compressed={was_compressed}).")

        return PromptPackage(
            assembled_prompt=full_prompt,
            system_instruction=self.DEFAULT_SYSTEM_INSTRUCTION,
            user_query=query_str,
            token_count_estimated=est_tokens,
            was_compressed=was_compressed,
            citations=citations,
        )
