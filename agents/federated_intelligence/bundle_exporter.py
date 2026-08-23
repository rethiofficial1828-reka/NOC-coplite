"""
Bundle Exporter Module for Federated Incident Intelligence Subsystem.

Assembles sanitized incident patterns into cryptographically signed JSON/ZIP knowledge bundles (.nockb / .json),
validates zero PII retention, and exports payloads for air-gapped USB/file transfer.
"""

import json
import os
from typing import List, Optional

from agents.core.logger import get_agent_logger
from agents.federated_intelligence.crypto_signer import CryptoSigner
from agents.federated_intelligence.federated_models import (
    BundleType,
    ExportBundleResult,
    ExportStatus,
    FederatedKnowledgeBundle,
    SanitizedIncident,
)
from agents.federated_intelligence.privacy_sanitizer import PrivacySanitizer

logger = get_agent_logger("BundleExporter")


class BundleExporter:
    """
    Bundle Exporter assembling and signing air-gapped knowledge bundles.
    """

    def __init__(
        self,
        source_site_id: str = "NOC-SITE-ALPHA",
        sanitizer: Optional[PrivacySanitizer] = None,
        signer: Optional[CryptoSigner] = None,
        export_dir: str = "data/federated_bundles",
    ) -> None:
        self.source_site_id = source_site_id
        self.sanitizer = sanitizer or PrivacySanitizer()
        self.signer = signer or CryptoSigner(signer_id=source_site_id)
        self.export_dir = export_dir
        os.makedirs(self.export_dir, exist_ok=True)

    def export_knowledge_bundle(
        self,
        sanitized_incidents: List[SanitizedIncident],
        bundle_type: BundleType = BundleType.INCIDENT_PATTERN_BUNDLE,
    ) -> ExportBundleResult:
        """
        Assemble, sign, and write a FederatedKnowledgeBundle file.

        Args:
            sanitized_incidents: List of sanitized incident records.
            bundle_type: Taxonomy type of bundle.

        Returns:
            ExportBundleResult.
        """
        if not sanitized_incidents:
            return ExportBundleResult(status=ExportStatus.FAILED, bundle_file_path="")

        # 1. Audit Privacy Verification on all incidents
        for inc in sanitized_incidents:
            is_clean, violations = self.sanitizer.verify_privacy_clean(inc.anonymized_pattern.root_cause_hypothesis)
            if not is_clean:
                logger.error(f"Export blocked! Privacy violations found in incident hypothesis: {violations}")
                return ExportBundleResult(status=ExportStatus.FAILED, bundle_file_path="")

        # 2. Extract unsigned payload dict for signature calculation
        incidents_dict = [inc.model_dump(mode="json") for inc in sanitized_incidents]
        payload_data = {
            "source_site_id": self.source_site_id,
            "bundle_type": bundle_type.value,
            "sanitized_incidents": incidents_dict,
        }

        # 3. Cryptographically sign payload
        signature = self.signer.sign_payload(payload_data)

        # 4. Construct complete bundle
        bundle = FederatedKnowledgeBundle(
            bundle_type=bundle_type,
            source_site_id=self.source_site_id,
            sanitized_incidents=sanitized_incidents,
            signature=signature,
        )

        # 5. Write to File
        file_path = os.path.join(self.export_dir, f"bundle_{bundle.bundle_id[:8]}.json")
        bundle_dict = bundle.model_dump(mode="json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(bundle_dict, f, indent=2)

        logger.info(f"BundleExporter created signed bundle file at '{file_path}' (Patterns: {len(sanitized_incidents)}).")

        return ExportBundleResult(
            bundle=bundle,
            status=ExportStatus.COMPLETED,
            bundle_file_path=file_path,
            total_patterns_exported=len(sanitized_incidents),
            signature_fingerprint=signature.signature_hex,
        )
