"""
Crypto Signer Module for Federated Incident Intelligence Subsystem.

Provides cryptographic signature generation and verification over canonicalized knowledge bundle payloads.
Ensures authenticity, tamper-resistance, and non-repudiation across air-gapped site boundaries.
"""

import hashlib
import hmac
import json
from typing import Any, Dict, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.federated_intelligence.federated_models import BundleSignature, SignatureAlgorithm

logger = get_agent_logger("CryptoSigner")

# Secret signing key for air-gapped demonstration / production default
DEFAULT_SECRET_KEY = b"NOC_COPILOT_FEDERATED_AIR_GAPPED_SECRET_KEY_2026"


class CryptoSigner:
    """
    Cryptographic Signer producing and verifying HMAC-SHA256 / SHA256 signatures over bundle content.
    """

    def __init__(self, signer_id: str = "NOC-SITE-ALPHA", secret_key: Optional[bytes] = None) -> None:
        self.signer_id = signer_id
        self.secret_key = secret_key or DEFAULT_SECRET_KEY

    def canonicalize(self, data: Dict[str, Any]) -> str:
        """
        Convert dict to deterministic, key-sorted JSON string for signature calculation.
        """
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def sign_payload(
        self,
        payload_data: Dict[str, Any],
        algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
    ) -> BundleSignature:
        """
        Generate cryptographic signature over payload dict.

        Args:
            payload_data: Data dictionary to sign.
            algorithm: SignatureAlgorithm to apply.

        Returns:
            BundleSignature object.
        """
        canonical_str = self.canonicalize(payload_data)

        if algorithm == SignatureAlgorithm.HMAC_SHA256:
            sig_hex = hmac.new(self.secret_key, canonical_str.encode("utf-8"), hashlib.sha256).hexdigest()
        else:
            # Fallback to SHA256 hash digest
            sig_hex = hashlib.sha256((canonical_str + self.secret_key.decode("utf-8")).encode("utf-8")).hexdigest()

        key_fp = hashlib.sha256(self.secret_key).hexdigest()[:16]

        sig = BundleSignature(
            signer_id=self.signer_id,
            algorithm=algorithm,
            signature_hex=sig_hex,
            public_key_fingerprint=key_fp,
        )

        logger.info(f"CryptoSigner signed payload for Signer '{self.signer_id}' (Sig: {sig_hex[:12]}...).")
        return sig

    def verify_signature(self, payload_data: Dict[str, Any], signature: BundleSignature) -> Tuple[bool, str]:
        """
        Verify signature against payload data.

        Returns:
            Tuple of (is_valid: bool, verification_message: str)
        """
        if not signature or not signature.signature_hex:
            return False, "Signature missing or empty"

        canonical_str = self.canonicalize(payload_data)

        if signature.algorithm == SignatureAlgorithm.HMAC_SHA256:
            expected_hex = hmac.new(self.secret_key, canonical_str.encode("utf-8"), hashlib.sha256).hexdigest()
        else:
            expected_hex = hashlib.sha256((canonical_str + self.secret_key.decode("utf-8")).encode("utf-8")).hexdigest()

        if hmac.compare_digest(signature.signature_hex, expected_hex):
            return True, f"Signature verified successfully for Signer '{signature.signer_id}'."
        else:
            logger.warning(f"Signature verification failed for Signer '{signature.signer_id}'. Payload tampered or invalid key.")
            return False, "Signature verification failed: payload modified or secret key mismatch."

    def sign_bundle_dict(self, bundle_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate signature payload dictionary over bundle dictionary.
        """
        payload_data = {
            "source_site_id": bundle_dict.get("source_site_id", self.signer_id),
            "bundle_type": bundle_dict.get("bundle_type", "INCIDENT_PATTERN_BUNDLE"),
            "sanitized_incidents": bundle_dict.get("sanitized_incidents", []),
        }
        sig = self.sign_payload(payload_data)
        return sig.model_dump(mode="json")
