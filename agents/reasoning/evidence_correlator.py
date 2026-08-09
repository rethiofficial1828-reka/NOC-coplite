"""
Evidence Correlator for Enterprise AI Reasoning Subsystem.

Collects, normalizes, deduplicates, and groups evidence items from Atomic Agents,
EvidenceRegistry, and InvestigationContext. Computes correlation matrices and
maintains evidence lineage graph.
"""

from collections import defaultdict
from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional, Set
import uuid

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.evidence_registry import EvidenceRegistry
from agents.orchestrator_ai.investigation_context import InvestigationContext
from agents.orchestrator_ai.investigation_models import EvidenceReference
from agents.reasoning.reasoning_models import (
    EvidenceCorrelation,
    EvidenceGroup,
    ReasoningEvidence,
)

logger = get_agent_logger("EvidenceCorrelator")


class EvidenceCorrelator:
    """
    Thread-safe engine for evidence collection, deduplication, correlation, and grouping.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def correlate(
        self,
        context: Optional[InvestigationContext] = None,
        evidence_registry: Optional[EvidenceRegistry] = None,
        raw_evidence_list: Optional[List[Any]] = None,
    ) -> EvidenceCorrelation:
        """
        Correlate and group evidence items from context, registry, or raw evidence lists.

        Returns:
            EvidenceCorrelation model containing correlated groups and matrix.
        """
        with self._lock:
            normalized_list: List[ReasoningEvidence] = []

            # 1. Ingest from EvidenceRegistry if available
            reg = evidence_registry or (context.evidence_registry if context else None)
            if reg:
                for ref in reg.get_all():
                    normalized_list.append(self._convert_reference(ref))

            # 2. Ingest from InvestigationContext agent outputs if available
            if context:
                for agent_name, output in context.get_all_agent_outputs().items():
                    normalized = self._convert_output(agent_name, output, context)
                    if normalized and not any(e.evidence_id == normalized.evidence_id for e in normalized_list):
                        normalized_list.append(normalized)

            # 3. Ingest raw items if passed
            if raw_evidence_list:
                for raw in raw_evidence_list:
                    converted = self._convert_raw(raw)
                    if converted:
                        normalized_list.append(converted)

            # 4. Deduplicate
            deduped_list = self._deduplicate(normalized_list)

            # 5. Group related evidence
            groups = self._group_evidence(deduped_list)

            # 6. Build Correlation Matrix between groups
            corr_matrix = self._build_correlation_matrix(groups)

            # 7. Extract key findings summary
            key_findings = self._extract_key_findings(groups)

            correlation = EvidenceCorrelation(
                correlation_id=str(uuid.uuid4()),
                groups=groups,
                total_evidence_count=len(deduped_list),
                correlation_matrix=corr_matrix,
                key_findings=key_findings,
                created_at=datetime.now(timezone.utc),
            )

            logger.info(
                f"EvidenceCorrelator processed {len(deduped_list)} evidence items "
                f"into {len(groups)} correlated groups."
            )
            return correlation

    def _convert_reference(self, ref: EvidenceReference) -> ReasoningEvidence:
        """Convert EvidenceReference to ReasoningEvidence."""
        return ReasoningEvidence(
            evidence_id=ref.evidence_id,
            source_agent=ref.source_agent,
            evidence_type=ref.evidence_type,
            confidence=ref.confidence,
            device_id=ref.device_id,
            timestamp=ref.timestamp,
            payload=dict(ref.payload),
            metadata={"parent_ids": list(ref.parent_evidence_ids)},
            normalized_score=ref.confidence,
        )

    def _convert_output(self, agent_name: str, output: Any, context: InvestigationContext) -> Optional[ReasoningEvidence]:
        """Convert raw agent output into ReasoningEvidence."""
        if not output:
            return None

        confidence = 0.85
        if hasattr(output, "confidence"):
            confidence = float(getattr(output, "confidence"))
        elif isinstance(output, dict) and "confidence" in output:
            confidence = float(output["confidence"])

        device_id = context.request.device_id if context and context.request else None
        payload = output.model_dump() if hasattr(output, "model_dump") else (output if isinstance(output, dict) else {"raw": str(output)})

        return ReasoningEvidence(
            evidence_id=f"evt-{agent_name.lower()}-{uuid.uuid4().hex[:8]}",
            source_agent=agent_name,
            evidence_type=agent_name.lower().replace("agent", ""),
            confidence=max(0.0, min(1.0, confidence)),
            device_id=device_id,
            timestamp=datetime.now(timezone.utc),
            payload=payload,
            normalized_score=confidence,
        )

    def _convert_raw(self, raw: Any) -> Optional[ReasoningEvidence]:
        """Convert arbitrary raw object into ReasoningEvidence."""
        if isinstance(raw, ReasoningEvidence):
            return raw
        elif isinstance(raw, EvidenceReference):
            return self._convert_reference(raw)
        elif isinstance(raw, dict):
            return ReasoningEvidence(
                source_agent=raw.get("source_agent", "UnknownAgent"),
                evidence_type=raw.get("evidence_type", "general"),
                confidence=float(raw.get("confidence", 0.8)),
                device_id=raw.get("device_id"),
                payload=raw.get("payload", dict(raw)),
            )
        return None

    def _deduplicate(self, evidence_list: List[ReasoningEvidence]) -> List[ReasoningEvidence]:
        """Remove exact duplicate evidence items by source and payload footprint."""
        unique: List[ReasoningEvidence] = []
        seen_footprints: Set[str] = set()

        for item in evidence_list:
            footprint = f"{item.source_agent}:{item.evidence_type}:{item.device_id}:{str(sorted(item.payload.items())) if isinstance(item.payload, dict) else str(item.payload)}"
            if footprint not in seen_footprints:
                seen_footprints.add(footprint)
                unique.append(item)

        return unique

    def _group_evidence(self, evidence_list: List[ReasoningEvidence]) -> List[EvidenceGroup]:
        """Group evidence items by device_id or primary evidence category."""
        groups_map: Dict[str, List[ReasoningEvidence]] = defaultdict(list)

        for item in evidence_list:
            group_key = item.device_id or item.evidence_type or "general"
            groups_map[group_key].append(item)

        groups: List[EvidenceGroup] = []
        for key, items in groups_map.items():
            ev_ids = [e.evidence_id for e in items]
            avg_conf = sum(e.confidence for e in items) / len(items) if items else 1.0
            primary_type = items[0].evidence_type if items else "general"
            summary_str = f"Correlated {len(items)} evidence items for '{key}' (avg_confidence={avg_conf:.2f})"

            group = EvidenceGroup(
                group_id=f"grp-{uuid.uuid4().hex[:8]}",
                group_name=f"Evidence Group: {key}",
                device_id=key if key != primary_type else None,
                primary_type=primary_type,
                evidence_ids=ev_ids,
                merged_confidence=avg_conf,
                summary=summary_str,
            )
            groups.append(group)

        return groups

    def _build_correlation_matrix(self, groups: List[EvidenceGroup]) -> Dict[str, Dict[str, float]]:
        """Build matrix computing similarity scores between evidence groups."""
        matrix: Dict[str, Dict[str, float]] = {}
        for g1 in groups:
            matrix[g1.group_id] = {}
            for g2 in groups:
                if g1.group_id == g2.group_id:
                    matrix[g1.group_id][g2.group_id] = 1.0
                else:
                    # Calculate similarity score based on overlapping device or type
                    score = 0.0
                    if g1.device_id and g1.device_id == g2.device_id:
                        score += 0.6
                    if g1.primary_type and g1.primary_type == g2.primary_type:
                        score += 0.4
                    matrix[g1.group_id][g2.group_id] = round(score, 2)
        return matrix

    def _extract_key_findings(self, groups: List[EvidenceGroup]) -> List[str]:
        """Extract high-level key findings from evidence groups."""
        findings = []
        for g in groups:
            findings.append(f"Identified {len(g.evidence_ids)} correlated evidence signal(s) in group '{g.group_name}'.")
        return findings
