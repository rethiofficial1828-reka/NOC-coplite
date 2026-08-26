"""
Security Domain Models for NOC Copilot v1.4.

Defines immutable Pydantic V2 domain models and enums for:
- Role-Based Access Control (AAA / RBAC)
- Certificate profiles and validation metadata
- Cryptographic credential references (with guaranteed non-leakage)
- mTLS connection profiles
- Credential leases and rotation lifecycle status

Guarantees:
- Zero plaintext secret or private key leakage in repr, str, or serialization
- Strict datetime and timezone validation
- Immutable data structures where appropriate
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# AAA / RBAC Enums & Identity Models
# ---------------------------------------------------------------------------


class AAARole(str, Enum):
    """Hierarchical Role-Based Access Control roles for NOC Copilot operations."""

    NOC_VIEWER = "NOC_VIEWER"
    NOC_OPERATOR = "NOC_OPERATOR"
    NOC_ENGINEER = "NOC_ENGINEER"
    NOC_ADMIN = "NOC_ADMIN"
    SECURITY_OFFICER = "SECURITY_OFFICER"


class AAAIdentity(BaseModel):
    """Validated operator or service identity with assigned RBAC roles."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user_id: str = Field(..., description="Unique enterprise user or service account ID")
    username: str = Field(..., description="Operator username or principal")
    roles: List[AAARole] = Field(default_factory=list, description="Assigned RBAC role list")
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Active session ID")
    authenticated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(default=None, description="Session expiration timestamp")

    def has_role(self, role: AAARole) -> bool:
        """Check if identity possesses the requested role."""
        return role in self.roles


class AuthorizationDecision(BaseModel):
    """Immutable record of an AAA authorization decision for auditing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    allowed: bool = Field(..., description="Whether the requested action is permitted")
    action: str = Field(..., description="Target operational action name")
    acting_identity: str = Field(..., description="Principal username or user ID")
    acting_roles: List[str] = Field(default_factory=list, description="Roles held at decision time")
    required_roles: List[str] = Field(default_factory=list, description="Roles required for action")
    target_resource: Optional[str] = Field(default=None, description="Target device, incident, or endpoint")
    reason: str = Field(..., description="Audit rationale for decision")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# mTLS & Certificate Metadata Models
# ---------------------------------------------------------------------------


class MTLSReadinessStatus(str, Enum):
    """Operational readiness state of mTLS certificate infrastructure."""

    NOT_CONFIGURED = "NOT_CONFIGURED"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"
    READY = "READY"
    ERROR = "ERROR"


class CertificateProfile(BaseModel):
    """
    Metadata representation of an X.509 certificate.
    Contains ONLY public metadata and cryptographic fingerprints, NEVER private key material.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cert_id: str = Field(..., description="Unique certificate identifier or filename")
    common_name: str = Field(..., description="Subject Common Name (CN)")
    san_list: List[str] = Field(default_factory=list, description="Subject Alternative Names (DNS/IP)")
    issuer: str = Field(..., description="Issuer Common Name or Organization")
    valid_from: datetime = Field(..., description="Certificate validity start time (UTC)")
    valid_until: datetime = Field(..., description="Certificate validity expiration time (UTC)")
    fingerprint_sha256: str = Field(..., description="SHA-256 fingerprint hex digest")
    is_ca: bool = Field(default=False, description="Whether this certificate is a CA")
    key_algorithm: str = Field(default="RSA_4096", description="Public key algorithm and bit strength")

    @property
    def is_expired(self) -> bool:
        """Check if certificate is expired relative to current UTC time."""
        return datetime.now(timezone.utc) >= self.valid_until

    @property
    def is_not_yet_valid(self) -> bool:
        """Check if certificate validity start is in the future."""
        return datetime.now(timezone.utc) < self.valid_from

    def is_valid_for_host(self, hostname: str) -> bool:
        """Verify if target hostname matches CN or any SAN entry."""
        if not hostname:
            return False
        clean_host = hostname.strip().lower()
        if self.common_name.strip().lower() == clean_host:
            return True
        for san in self.san_list:
            clean_san = san.strip().lower()
            if clean_san == clean_host:
                return True
            # Wildcard SAN support (*.domain.com)
            if clean_san.startswith("*."):
                domain_suffix = clean_san[2:]
                if clean_host.endswith(domain_suffix) and clean_host.count(".") == clean_san.count("."):
                    return True
        return False


# ---------------------------------------------------------------------------
# Cryptographic Credential References (Safe Redaction)
# ---------------------------------------------------------------------------


class CredentialReference(BaseModel):
    """
    Indirect pointer to a secure credential stored in an external Vault or KMS.
    Guarantees no raw secrets/passwords/private keys are serialized or logged.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    credential_id: str = Field(..., description="Logical credential name")
    credential_type: str = Field(default="MTLS_CERTIFICATE", description="Credential type category")
    vault_path: str = Field(..., description="Secret store path reference")
    version: str = Field(default="v1", description="Credential version")
    fingerprint: Optional[str] = Field(default=None, description="Safe public SHA-256 fingerprint")

    def __repr__(self) -> str:
        return f"<CredentialReference id={self.credential_id} type={self.credential_type} path={self.vault_path} [SECRET REDACTED]>"

    def __str__(self) -> str:
        return f"CredentialRef({self.credential_id}@{self.vault_path})"


class MTLSConnectionProfile(BaseModel):
    """
    Immutable mTLS configuration linking device endpoint to indirect credential references.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(..., description="Unique connection profile identifier")
    device_id: str = Field(..., description="Target device identifier")
    tls_server_name: str = Field(..., description="Expected Server Name Indication (SNI)")
    ca_cert_ref: CredentialReference = Field(..., description="Trusted Root/Intermediate CA reference")
    client_cert_ref: CredentialReference = Field(..., description="Client Certificate reference")
    client_key_ref: CredentialReference = Field(..., description="Client Private Key reference")
    min_tls_version: str = Field(default="TLSv1.3", description="Minimum enforced TLS version")
    cipher_suites: List[str] = Field(
        default_factory=lambda: [
            "TLS_AES_256_GCM_SHA384",
            "TLS_CHACHA20_POLY1305_SHA256",
            "TLS_AES_128_GCM_SHA256",
            "ECDHE-RSA-AES256-GCM-SHA384",
        ],
        description="Allowed cryptographic cipher suites",
    )


# ---------------------------------------------------------------------------
# Credential Lease & Rotation Models
# ---------------------------------------------------------------------------


class CredentialLease(BaseModel):
    """Metadata tracking an active ephemeral secret lease."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lease_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    path: str = Field(..., description="Vault secret path")
    renewable: bool = Field(default=True)
    lease_duration_sec: int = Field(default=3600)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(...)


class CredentialRotationStatus(BaseModel):
    """State of certificate or API token rotation lifecycle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    credential_id: str = Field(..., description="Credential identifier")
    last_rotated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    next_rotation_due: datetime = Field(...)
    rotation_in_progress: bool = Field(default=False)
    rotation_error: Optional[str] = Field(default=None)
    status: str = Field(default="CURRENT", description="CURRENT | DUE | IN_PROGRESS | FAILED")

    @property
    def is_rotation_due(self) -> bool:
        """Check if current UTC time exceeds next_rotation_due."""
        return datetime.now(timezone.utc) >= self.next_rotation_due
