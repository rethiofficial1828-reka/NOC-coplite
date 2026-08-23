"""
Federated Knowledge Base Manager Module.

Indexes validated, anonymized federated incident patterns into local RAG/VectorStore storage.
Allows local NOC Copilot incident reasoning to match incoming symptoms against federated cross-site operational patterns.
"""

import json
import os
import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.federated_intelligence.federated_models import (
    AnonymizedPattern,
    FederatedKnowledgeBundle,
    TrustOrigin,
)

logger = get_agent_logger("FederatedKnowledgeBaseManager")


class FederatedKnowledgeBaseManager:
    """
    Knowledge Base Manager for federated cross-site incident pattern indexing and local RAG retrieval.
    """

    def __init__(self, index_file: str = "data/federated_knowledge_index.json") -> None:
        self.index_file = index_file
        self._lock = threading.RLock()
        self._patterns: List[Dict[str, Any]] = []
        os.makedirs(os.path.dirname(self.index_file), exist_ok=True)
        self._load_index()

    def _load_index(self) -> None:
        """Load stored patterns from JSON index file."""
        with self._lock:
            if os.path.exists(self.index_file):
                try:
                    with open(self.index_file, "r", encoding="utf-8") as f:
                        self._patterns = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load federated knowledge index file: {e}")
                    self._patterns = []
            else:
                self._patterns = []

    def _save_index(self) -> None:
        """Save patterns to JSON index file."""
        with self._lock:
            try:
                with open(self.index_file, "w", encoding="utf-8") as f:
                    json.dump(self._patterns, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save federated knowledge index file: {e}")

    def index_bundle_patterns(
        self,
        bundle: FederatedKnowledgeBundle,
        trust_origin: TrustOrigin = TrustOrigin.FEDERATED_SITE_ALPHA,
    ) -> int:
        """
        Index sanitized incident patterns from a verified bundle into the local RAG knowledge base.

        Args:
            bundle: Verified FederatedKnowledgeBundle.
            trust_origin: Origin classification.

        Returns:
            Number of new patterns indexed.
        """
        with self._lock:
            added_count = 0
            existing_ids = {p.get("pattern_id") for p in self._patterns if "pattern_id" in p}

            for inc in bundle.sanitized_incidents:
                pattern = inc.anonymized_pattern
                if pattern.pattern_id not in existing_ids:
                    record = {
                        "pattern_id": pattern.pattern_id,
                        "category": pattern.category,
                        "symptoms": pattern.symptoms,
                        "structural_signals": pattern.structural_signals,
                        "root_cause_hypothesis": pattern.root_cause_hypothesis,
                        "recommended_action": pattern.recommended_action,
                        "confidence_score": pattern.confidence_score,
                        "source_site_id": bundle.source_site_id,
                        "trust_origin": trust_origin.value,
                        "bundle_id": bundle.bundle_id,
                        "indexed_at": bundle.created_at.isoformat(),
                    }
                    self._patterns.append(record)
                    existing_ids.add(pattern.pattern_id)
                    added_count += 1

            if added_count > 0:
                self._save_index()
                logger.info(f"Indexed {added_count} new federated patterns from Bundle '{bundle.bundle_id[:8]}' (Origin: {trust_origin.value}).")

            return added_count

    def search_federated_patterns(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Perform keyword/similarity RAG search against indexed federated patterns.

        Args:
            query: Search query text or symptom description.
            category: Optional filter by category.
            top_k: Maximum matches to return.

        Returns:
            List of matching pattern dictionary records.
        """
        with self._lock:
            query_lower = query.lower()
            matches = []

            for p in self._patterns:
                if category and p.get("category", "").lower() != category.lower():
                    continue

                # Calculate score based on symptom and hypothesis matching
                score = 0.0
                hypo = p.get("root_cause_hypothesis", "").lower()
                rec = p.get("recommended_action", "").lower()
                cat = p.get("category", "").lower()
                symptoms = " ".join(p.get("symptoms", [])).lower()

                if query_lower in hypo:
                    score += 0.5
                if query_lower in symptoms:
                    score += 0.4
                if query_lower in rec or query_lower in cat:
                    score += 0.2

                if score > 0 or not query:
                    match_record = dict(p)
                    match_record["search_relevance_score"] = round(min(1.0, score + 0.5), 2)
                    matches.append(match_record)

            matches.sort(key=lambda x: x.get("search_relevance_score", 0.0), reverse=True)
            return matches[:top_k]

    def get_indexed_count(self) -> int:
        """Return total number of indexed federated patterns."""
        with self._lock:
            return len(self._patterns)
