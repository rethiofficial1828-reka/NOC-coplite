"""
Federated Intelligence Service Module.

Primary domain orchestration service coordinating PrivacySanitizer, CryptoSigner, BundleExporter, BundleImporter,
and FederatedKnowledgeBaseManager into a unified air-gapped federated knowledge exchange pipeline.
"""

import threading
from typing import Any, Dict, List, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.federated_intelligence.bundle_exporter import BundleExporter
from agents.federated_intelligence.bundle_importer import BundleImporter
from agents.federated_intelligence.crypto_signer import CryptoSigner
from agents.federated_intelligence.federated_knowledge_base import FederatedKnowledgeBaseManager
from agents.federated_intelligence.federated_models import (
    BundleType,
    ExportBundleResult,
    FederatedIntelligenceStatistics,
    ImportStatus,
    ImportValidationResult,
    SanitizationLevel,
    TrustOrigin,
)
from agents.federated_intelligence.privacy_sanitizer import PrivacySanitizer

logger = get_agent_logger("FederatedIntelligenceService")


class FederatedIntelligenceService:
    """
    Domain Orchestration Service for Sprint 20 Federated Incident Intelligence Subsystem.
    """

    def __init__(
        self,
        site_id: str = "NOC-SITE-ALPHA",
        sanitizer: Optional[PrivacySanitizer] = None,
        signer: Optional[CryptoSigner] = None,
        exporter: Optional[BundleExporter] = None,
        importer: Optional[BundleImporter] = None,
        kb_manager: Optional[FederatedKnowledgeBaseManager] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.site_id = site_id
        self.sanitizer = sanitizer or PrivacySanitizer()
        self.signer = signer or CryptoSigner(signer_id=site_id)
        self.exporter = exporter or BundleExporter(source_site_id=site_id, sanitizer=self.sanitizer, signer=self.signer)
        self.importer = importer or BundleImporter(sanitizer=self.sanitizer, signer=self.signer)
        self.kb_manager = kb_manager or FederatedKnowledgeBaseManager()
        self.event_bus = event_bus

        self._stats = FederatedIntelligenceStatistics()
        self._lock = threading.RLock()

    def export_incident_intelligence(
        self,
        raw_symptoms: List[str],
        category: str,
        hypothesis: str,
        recommendation: str,
        bundle_type: BundleType = BundleType.INCIDENT_PATTERN_BUNDLE,
        level: SanitizationLevel = SanitizationLevel.STRICT,
    ) -> ExportBundleResult:
        """
        Sanitize, sign, assemble, and export offline knowledge bundle.
        """
        with self._lock:
            # 1. Privacy Sanitization
            sanitized_inc = self.sanitizer.sanitize_incident(
                raw_symptoms=raw_symptoms,
                category=category,
                hypothesis=hypothesis,
                recommendation=recommendation,
                level=level,
            )

            # 2. Bundle Assembly & Signing
            res = self.exporter.export_knowledge_bundle([sanitized_inc], bundle_type=bundle_type)

            if res.status.value == "COMPLETED":
                self._stats.total_bundles_exported += 1
                if self.event_bus:
                    self._publish_event("federated.bundle.exported", {"bundle_id": res.bundle.bundle_id if res.bundle else "", "file_path": res.bundle_file_path})

            logger.info(f"FederatedIntelligenceService export completed: Status = {res.status.value}, File = '{res.bundle_file_path}'")
            return res

    def import_and_index_bundle(
        self,
        file_path_or_dict: Any,
        trust_origin: TrustOrigin = TrustOrigin.FEDERATED_SITE_ALPHA,
    ) -> ImportValidationResult:
        """
        Validate, audit signature & privacy, and index external bundle into local RAG knowledge base.
        """
        with self._lock:
            bundle, val_res = self.importer.import_and_validate_bundle(file_path_or_dict)

            if val_res.status == ImportStatus.VALIDATED_AND_IMPORTED and bundle:
                indexed_count = self.kb_manager.index_bundle_patterns(bundle, trust_origin=trust_origin)
                val_res.patterns_imported_count = indexed_count

                self._stats.total_bundles_imported += 1
                self._stats.total_federated_patterns_indexed += indexed_count

                if self.event_bus:
                    self._publish_event("federated.bundle.imported", {"bundle_id": bundle.bundle_id, "patterns_indexed": indexed_count})
            else:
                if not val_res.signature_valid:
                    self._stats.signature_failures += 1
                if not val_res.privacy_valid:
                    self._stats.privacy_violations_blocked += 1

            logger.info(f"FederatedIntelligenceService import completed: Status = {val_res.status.value}, Patterns Indexed = {val_res.patterns_imported_count}")
            return val_res

    def query_federated_knowledge(self, query: str, category: Optional[str] = None, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search local RAG vector index for federated incident patterns.
        """
        with self._lock:
            matches = self.kb_manager.search_federated_patterns(query=query, category=category, top_k=top_k)
            if matches:
                self._stats.local_rag_matches += len(matches)
            return matches

    def get_statistics(self) -> FederatedIntelligenceStatistics:
        """Return subsystem execution metrics."""
        with self._lock:
            self._stats.total_federated_patterns_indexed = self.kb_manager.get_indexed_count()
            return self._stats

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Helper to publish EventBus events."""
        if self.event_bus:
            try:
                evt = Event(event_type=event_type, source="FederatedIntelligenceService", payload=payload)
                self.event_bus.publish(evt)
            except Exception as e:
                logger.warning(f"EventBus publish error for '{event_type}': {e}")
