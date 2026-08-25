"""
Thread-Safe Evidence Registry for Enterprise AI Investigation Platform.

Registers, tracks, queries, and maintains lineage for all evidence items produced
by Atomic Agents during investigation workflows.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.orchestrator_ai.investigation_models import EvidenceReference

logger = get_agent_logger("EvidenceRegistry")


class EvidenceRegistry:
    """
    Thread-safe repository for evidence items and evidence lineage tracking.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._evidence: Dict[str, EvidenceReference] = {}
        self._by_source: Dict[str, List[str]] = {}
        self._by_device: Dict[str, List[str]] = {}
        self._by_incident: Dict[str, List[str]] = {}
        self._by_type: Dict[str, List[str]] = {}
        self._by_relationship: Dict[str, List[str]] = {}
        self._by_provenance: Dict[str, List[str]] = {}
        self._by_linked_decision: Dict[str, List[str]] = {}

    def register_evidence(self, evidence: EvidenceReference) -> str:
        """
        Register a pre-constructed EvidenceReference object.

        Args:
            evidence: Strongly-typed EvidenceReference model.

        Returns:
            Unique evidence ID string.
        """
        with self._lock:
            eid = evidence.evidence_id
            self._evidence[eid] = evidence

            # Index by source
            if evidence.source_agent not in self._by_source:
                self._by_source[evidence.source_agent] = []
            self._by_source[evidence.source_agent].append(eid)

            # Index by type
            if evidence.evidence_type not in self._by_type:
                self._by_type[evidence.evidence_type] = []
            self._by_type[evidence.evidence_type].append(eid)

            # Index by device if present
            if evidence.device_id:
                if evidence.device_id not in self._by_device:
                    self._by_device[evidence.device_id] = []
                self._by_device[evidence.device_id].append(eid)

            # Index by incident if present
            if evidence.incident_id:
                if evidence.incident_id not in self._by_incident:
                    self._by_incident[evidence.incident_id] = []
                self._by_incident[evidence.incident_id].append(eid)

            # Index by relationship
            rel = (evidence.relationship or "SUPPORTING").upper()
            if rel not in self._by_relationship:
                self._by_relationship[rel] = []
            self._by_relationship[rel].append(eid)

            # Index by provenance
            prov = (evidence.provenance or "OBSERVED").upper()
            if prov not in self._by_provenance:
                self._by_provenance[prov] = []
            self._by_provenance[prov].append(eid)

            # Index by linked decision if present
            if evidence.linked_decision:
                ld = evidence.linked_decision
                if ld not in self._by_linked_decision:
                    self._by_linked_decision[ld] = []
                self._by_linked_decision[ld].append(eid)

            logger.debug(
                f"Registered evidence '{eid}' from agent '{evidence.source_agent}' "
                f"(type={evidence.evidence_type}, prov={prov}, rel={rel}, confidence={evidence.confidence:.2f})"
            )
            return eid

    def register(
        self,
        source_agent: str,
        evidence_type: str,
        payload: Dict[str, Any],
        confidence: float = 1.0,
        device_id: Optional[str] = None,
        incident_id: Optional[str] = None,
        topology_ref: Optional[Dict[str, Any]] = None,
        runbook_ref: Optional[Dict[str, Any]] = None,
        parent_evidence_ids: Optional[List[str]] = None,
        provenance: str = "OBSERVED",
        relationship: str = "SUPPORTING",
        affected_entity: Optional[str] = None,
        linked_decision: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> EvidenceReference:
        """
        Construct and register a new evidence item.

        Returns:
            Created EvidenceReference object.
        """
        evidence = EvidenceReference(
            evidence_id=str(uuid.uuid4()),
            source_agent=source_agent,
            evidence_type=evidence_type,
            confidence=max(0.0, min(1.0, confidence)),
            provenance=provenance,
            relationship=relationship,
            device_id=device_id,
            affected_entity=affected_entity or device_id,
            linked_decision=linked_decision,
            summary=summary,
            incident_id=incident_id,
            topology_ref=topology_ref,
            runbook_ref=runbook_ref,
            timestamp=datetime.now(timezone.utc),
            payload=payload,
            parent_evidence_ids=parent_evidence_ids or [],
        )
        self.register_evidence(evidence)
        return evidence

    def get_evidence(self, evidence_id: str) -> Optional[EvidenceReference]:
        """Fetch an evidence reference by ID."""
        with self._lock:
            ref = self._evidence.get(evidence_id)
            return ref.model_copy() if ref else None

    def get_by_source(self, source_agent: str) -> List[EvidenceReference]:
        """Fetch all evidence items produced by a specific agent."""
        with self._lock:
            ids = self._by_source.get(source_agent, [])
            return [self._evidence[i].model_copy() for i in ids if i in self._evidence]

    def get_by_device(self, device_id: str) -> List[EvidenceReference]:
        """Fetch evidence related to a specific device."""
        with self._lock:
            ids = self._by_device.get(device_id, [])
            return [self._evidence[i].model_copy() for i in ids if i in self._evidence]

    def get_by_incident(self, incident_id: str) -> List[EvidenceReference]:
        """Fetch evidence related to a specific incident."""
        with self._lock:
            ids = self._by_incident.get(incident_id, [])
            return [self._evidence[i].model_copy() for i in ids if i in self._evidence]

    def get_by_type(self, evidence_type: str) -> List[EvidenceReference]:
        """Fetch evidence items of a specific type."""
        with self._lock:
            ids = self._by_type.get(evidence_type, [])
            return [self._evidence[i].model_copy() for i in ids if i in self._evidence]

    def get_by_relationship(self, relationship: str) -> List[EvidenceReference]:
        """Fetch evidence items by relationship (e.g. SUPPORTING, CONTRADICTING, UNRESOLVED, NEUTRAL)."""
        with self._lock:
            ids = self._by_relationship.get(relationship.upper(), [])
            return [self._evidence[i].model_copy() for i in ids if i in self._evidence]

    def get_by_provenance(self, provenance: str) -> List[EvidenceReference]:
        """Fetch evidence items by provenance (e.g. OBSERVED, PREDICTED, INFERRED, HISTORICAL, SIMULATION)."""
        with self._lock:
            ids = self._by_provenance.get(provenance.upper(), [])
            return [self._evidence[i].model_copy() for i in ids if i in self._evidence]

    def get_by_linked_decision(self, linked_decision: str) -> List[EvidenceReference]:
        """Fetch evidence items linked to a specific decision or conclusion."""
        with self._lock:
            ids = self._by_linked_decision.get(linked_decision, [])
            return [self._evidence[i].model_copy() for i in ids if i in self._evidence]

    def get_all(self) -> List[EvidenceReference]:
        """Fetch copy of all registered evidence items."""
        with self._lock:
            return [e.model_copy() for e in self._evidence.values()]

    def get_lineage(self, evidence_id: str) -> List[EvidenceReference]:
        """
        Recursively trace ancestor evidence lineage for a given evidence item.

        Returns:
            Ordered list of ancestor EvidenceReference objects (oldest first).
        """
        with self._lock:
            lineage: List[EvidenceReference] = []
            visited = set()
            queue = [evidence_id]

            while queue:
                curr_id = queue.pop(0)
                if curr_id in visited or curr_id not in self._evidence:
                    continue
                visited.add(curr_id)
                item = self._evidence[curr_id]
                if curr_id != evidence_id:
                    lineage.append(item.model_copy())
                queue.extend(item.parent_evidence_ids)

            lineage.reverse()
            return lineage

    def clear(self) -> None:
        """Clear all registered evidence."""
        with self._lock:
            self._evidence.clear()
            self._by_source.clear()
            self._by_device.clear()
            self._by_incident.clear()
            self._by_type.clear()
            self._by_relationship.clear()
            self._by_provenance.clear()
            self._by_linked_decision.clear()
            logger.debug("EvidenceRegistry cleared.")
