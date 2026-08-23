"""
Bundle Importer Module for Federated Incident Intelligence Subsystem.

Ingests, validates, and audits imported external knowledge bundles. Performs multi-stage cryptographic signature
verification, schema validation, and strict PII privacy audit prior to permitting local RAG/VectorStore ingestion.
"""

import json
import os
from typing import Any, Dict, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.federated_intelligence.crypto_signer import CryptoSigner
from agents.federated_intelligence.federated_models import (
    BundleSignature,
    FederatedKnowledgeBundle,
    ImportStatus,
    ImportValidationResult,
)
from agents.federated_intelligence.privacy_sanitizer import PrivacySanitizer

logger = get_agent_logger("BundleImporter")


class BundleImporter:
    """
    Bundle Importer enforcing cryptographic signature verification and PII compliance audits.
    """

    def __init__(
        self,
        sanitizer: Optional[PrivacySanitizer] = None,
        signer: Optional[CryptoSigner] = None,
    ) -> None:
        self.sanitizer = sanitizer or PrivacySanitizer()
        self.signer = signer or CryptoSigner()

    def import_and_validate_bundle(self, file_path_or_dict: Any) -> Tuple[Optional[FederatedKnowledgeBundle], ImportValidationResult]:
        """
        Import external knowledge bundle from JSON file path or dictionary.

        Args:
            file_path_or_dict: String file path or dict payload.

        Returns:
            Tuple of (FederatedKnowledgeBundle or None, ImportValidationResult)
        """
        raw_dict: Dict[str, Any] = {}
        if isinstance(file_path_or_dict, str):
            if not os.path.exists(file_path_or_dict):
                return None, ImportValidationResult(
                    bundle_id="UNKNOWN",
                    status=ImportStatus.REJECTED,
                    messages=[f"File not found: '{file_path_or_dict}'"],
                )
            try:
                with open(file_path_or_dict, "r", encoding="utf-8") as f:
                    raw_dict = json.load(f)
            except Exception as e:
                return None, ImportValidationResult(
                    bundle_id="UNKNOWN",
                    status=ImportStatus.SCHEMA_INVALID,
                    messages=[f"JSON parsing error: {e}"],
                )
        elif isinstance(file_path_or_dict, dict):
            raw_dict = file_path_or_dict
        else:
            return None, ImportValidationResult(bundle_id="UNKNOWN", status=ImportStatus.REJECTED, messages=["Invalid payload type"])

        # 1. Schema Validation
        try:
            bundle = FederatedKnowledgeBundle.model_validate(raw_dict)
        except Exception as e:
            logger.warning(f"Bundle schema validation failed: {e}")
            return None, ImportValidationResult(
                bundle_id=raw_dict.get("bundle_id", "UNKNOWN"),
                status=ImportStatus.SCHEMA_INVALID,
                schema_valid=False,
                messages=[f"Schema validation error: {e}"],
            )

        # 2. Cryptographic Signature Verification
        # Use raw_dict["sanitized_incidents"] — the original as-received JSON list —
        # as the verification payload.  This matches the canonical payload that the
        # signer computed the HMAC over.  Using model_dump() here would inject
        # Pydantic-generated default fields (pattern_id, structural_signals,
        # confidence_score, sanitized_timestamp, sanitization_level,
        # anonymized_metadata) that were absent from the signing dict, causing an
        # HMAC mismatch.  Schema validation (step 1 above) has already confirmed the
        # raw payload is structurally valid, so this is safe.
        payload_data = {
            "source_site_id": bundle.source_site_id,
            "bundle_type": bundle.bundle_type.value,
            "sanitized_incidents": raw_dict.get("sanitized_incidents", []),
        }

        sig_ok, sig_msg = self.signer.verify_signature(payload_data, bundle.signature)
        if not sig_ok:
            logger.error(f"Bundle {bundle.bundle_id[:8]} rejected: Signature verification failed!")
            return None, ImportValidationResult(
                bundle_id=bundle.bundle_id,
                status=ImportStatus.SIGNATURE_VERIFICATION_FAILED,
                signature_valid=False,
                schema_valid=True,
                messages=[f"Signature validation failed: {sig_msg}"],
            )

        # 3. Privacy PII Audit Verification
        privacy_violations = []
        for inc in bundle.sanitized_incidents:
            is_clean, violations = self.sanitizer.verify_privacy_clean(inc.anonymized_pattern.root_cause_hypothesis)
            if not is_clean:
                privacy_violations.extend(violations)

        if privacy_violations:
            logger.error(f"Bundle {bundle.bundle_id[:8]} rejected: Privacy violations detected! ({privacy_violations})")
            return None, ImportValidationResult(
                bundle_id=bundle.bundle_id,
                status=ImportStatus.PRIVACY_CHECK_FAILED,
                signature_valid=True,
                privacy_valid=False,
                schema_valid=True,
                messages=[f"Privacy PII audit failed: {v}" for v in privacy_violations],
            )

        # 4. Validated and Approved for Ingestion
        count = len(bundle.sanitized_incidents)
        logger.info(f"Bundle {bundle.bundle_id[:8]} validated successfully! ({count} patterns approved for import).")

        res = ImportValidationResult(
            bundle_id=bundle.bundle_id,
            status=ImportStatus.VALIDATED_AND_IMPORTED,
            signature_valid=True,
            privacy_valid=True,
            schema_valid=True,
            patterns_imported_count=count,
            messages=["Bundle validation and privacy audit PASSED clean."],
        )

        return bundle, res
