"""
mTLS & Certificate Authority Validation Module for NOC Copilot v1.4.

Defines:
- CertificateAuthorityValidator: Performs strict cryptographic metadata and X.509 sanity checks.
- MTLSManager: Manages connection profiles, CA trust stores, and client certificate readiness without network connections.

Guarantees:
- Zero raw socket / remote network connections
- Strict SAN/Hostname matching
- Expiration and validity window enforcement
- Chain validation metadata verification
- Zero private key material exposure
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from agents.core.logger import get_agent_logger
from agents.security.security_models import (
    CertificateProfile,
    MTLSConnectionProfile,
    MTLSReadinessStatus,
)

logger = get_agent_logger("MTLSManager")


class CertificateAuthorityValidator:
    """
    Validates X.509 certificate profiles against enterprise PKI and mTLS standards.
    """

    @staticmethod
    def validate_ca_certificate(ca_cert: CertificateProfile) -> Tuple[bool, List[str]]:
        """Validate Root or Intermediate CA certificate metadata."""
        errors: List[str] = []

        if not ca_cert.is_ca:
            errors.append(f"Certificate '{ca_cert.cert_id}' is not designated as a Certificate Authority (is_ca=False).")

        if ca_cert.is_expired:
            errors.append(f"CA Certificate '{ca_cert.cert_id}' expired at {ca_cert.valid_until.isoformat()}.")

        if ca_cert.is_not_yet_valid:
            errors.append(f"CA Certificate '{ca_cert.cert_id}' is not yet valid (starts {ca_cert.valid_from.isoformat()}).")

        if not ca_cert.fingerprint_sha256 or len(ca_cert.fingerprint_sha256) < 32:
            errors.append(f"CA Certificate '{ca_cert.cert_id}' has missing or invalid SHA-256 fingerprint.")

        return len(errors) == 0, errors

    @staticmethod
    def validate_client_certificate(client_cert: CertificateProfile) -> Tuple[bool, List[str]]:
        """Validate Client certificate metadata for mTLS mutual authentication."""
        errors: List[str] = []

        if client_cert.is_expired:
            errors.append(f"Client Certificate '{client_cert.cert_id}' expired at {client_cert.valid_until.isoformat()}.")

        if client_cert.is_not_yet_valid:
            errors.append(f"Client Certificate '{client_cert.cert_id}' is not yet valid (starts {client_cert.valid_from.isoformat()}).")

        if not client_cert.common_name or not client_cert.common_name.strip():
            errors.append(f"Client Certificate '{client_cert.cert_id}' has empty Subject Common Name.")

        if not client_cert.fingerprint_sha256 or len(client_cert.fingerprint_sha256) < 32:
            errors.append(f"Client Certificate '{client_cert.cert_id}' has missing or invalid SHA-256 fingerprint.")

        return len(errors) == 0, errors

    @staticmethod
    def validate_server_name(server_cert: CertificateProfile, expected_server_name: str) -> Tuple[bool, List[str]]:
        """Verify that server certificate Subject CN / SAN covers the expected hostname."""
        errors: List[str] = []

        if not expected_server_name or not expected_server_name.strip():
            errors.append("Expected server name is empty.")
            return False, errors

        if not server_cert.is_valid_for_host(expected_server_name):
            errors.append(
                f"Server certificate '{server_cert.cert_id}' does not match expected host '{expected_server_name}'. "
                f"(CN: '{server_cert.common_name}', SANs: {server_cert.san_list})"
            )

        return len(errors) == 0, errors

    @classmethod
    def validate_certificate_chain(
        cls, client_cert: CertificateProfile, ca_cert: CertificateProfile
    ) -> Tuple[bool, List[str]]:
        """Validate that client certificate is issued by the declared CA and dates align."""
        errors: List[str] = []

        # Validate both individual certs
        ca_ok, ca_errs = cls.validate_ca_certificate(ca_cert)
        errors.extend(ca_errs)

        client_ok, client_errs = cls.validate_client_certificate(client_cert)
        errors.extend(client_errs)

        # Validate issuer link
        if client_cert.issuer.strip().lower() != ca_cert.common_name.strip().lower():
            errors.append(
                f"Certificate chain mismatch: Client issuer '{client_cert.issuer}' does not match CA Subject '{ca_cert.common_name}'."
            )

        # Validate validity window nesting
        if client_cert.valid_until > ca_cert.valid_until:
            errors.append(
                f"Client cert expires ({client_cert.valid_until.isoformat()}) after CA cert ({ca_cert.valid_until.isoformat()})."
            )

        return len(errors) == 0, errors


class MTLSManager:
    """
    Manages enterprise mTLS trust configurations, client certificates, and readiness validation.
    """

    def __init__(self) -> None:
        self._validator = CertificateAuthorityValidator()
        self._ca_registry: Dict[str, CertificateProfile] = {}
        self._client_cert_registry: Dict[str, CertificateProfile] = {}
        self._connection_profiles: Dict[str, MTLSConnectionProfile] = {}

    def register_ca_profile(self, profile: CertificateProfile) -> None:
        """Register a trusted CA profile."""
        self._ca_registry[profile.cert_id] = profile
        logger.info(f"Registered CA Profile '{profile.cert_id}' (CN: {profile.common_name}).")

    def register_client_profile(self, profile: CertificateProfile) -> None:
        """Register a client certificate profile."""
        self._client_cert_registry[profile.cert_id] = profile
        logger.info(f"Registered Client Certificate Profile '{profile.cert_id}' (CN: {profile.common_name}).")

    def register_connection_profile(self, profile: MTLSConnectionProfile) -> None:
        """Register a device mTLS connection profile."""
        self._connection_profiles[profile.device_id] = profile
        logger.info(f"Registered mTLS Connection Profile for device '{profile.device_id}'.")

    def validate_connection(self, device_id: str) -> Tuple[bool, List[str]]:
        """Validate that a device's configured mTLS profile has all required, valid certificates."""
        errors: List[str] = []

        if device_id not in self._connection_profiles:
            errors.append(f"No mTLS connection profile registered for device '{device_id}'.")
            return False, errors

        profile = self._connection_profiles[device_id]

        # Check CA
        ca_id = profile.ca_cert_ref.credential_id
        if ca_id not in self._ca_registry:
            errors.append(f"Referenced CA certificate '{ca_id}' is not registered in trust store.")
            return False, errors
        ca_cert = self._ca_registry[ca_id]

        # Check Client Cert
        client_id = profile.client_cert_ref.credential_id
        if client_id not in self._client_cert_registry:
            errors.append(f"Referenced Client certificate '{client_id}' is not registered.")
            return False, errors
        client_cert = self._client_cert_registry[client_id]

        # Validate chain
        chain_ok, chain_errs = self._validator.validate_certificate_chain(client_cert, ca_cert)
        errors.extend(chain_errs)

        return len(errors) == 0, errors

    def check_readiness(self, device_id: Optional[str] = None) -> MTLSReadinessStatus:
        """Evaluate operational readiness status for a specific device or entire registry."""
        if not self._ca_registry or not self._client_cert_registry:
            return MTLSReadinessStatus.NOT_CONFIGURED

        if device_id is not None:
            if device_id not in self._connection_profiles:
                return MTLSReadinessStatus.NOT_CONFIGURED
            is_valid, errors = self.validate_connection(device_id)
            if not is_valid:
                for err in errors:
                    if "expired" in err.lower():
                        return MTLSReadinessStatus.EXPIRED
                return MTLSReadinessStatus.INVALID
            return MTLSReadinessStatus.READY

        # Evaluate fleet readiness
        has_any_expired = any(c.is_expired for c in self._ca_registry.values()) or any(
            c.is_expired for c in self._client_cert_registry.values()
        )
        if has_any_expired:
            return MTLSReadinessStatus.EXPIRED

        return MTLSReadinessStatus.READY

    def get_safe_status_summary(self) -> Dict[str, Any]:
        """Return safe, non-sensitive public metadata summary for health reporting."""
        return {
            "total_ca_certs": len(self._ca_registry),
            "total_client_certs": len(self._client_cert_registry),
            "total_connection_profiles": len(self._connection_profiles),
            "readiness_status": self.check_readiness().value,
            "ca_certificates": [
                {
                    "cert_id": c.cert_id,
                    "common_name": c.common_name,
                    "issuer": c.issuer,
                    "valid_until": c.valid_until.isoformat(),
                    "fingerprint": c.fingerprint_sha256[:16] + "...",
                    "is_expired": c.is_expired,
                }
                for c in self._ca_registry.values()
            ],
            "client_certificates": [
                {
                    "cert_id": c.cert_id,
                    "common_name": c.common_name,
                    "valid_until": c.valid_until.isoformat(),
                    "fingerprint": c.fingerprint_sha256[:16] + "...",
                    "is_expired": c.is_expired,
                }
                for c in self._client_cert_registry.values()
            ],
        }
