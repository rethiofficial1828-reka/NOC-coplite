"""
Federated Models Module for Enterprise Air-Gapped Federated Incident Intelligence & Signed Knowledge Exchange.

Defines Pydantic V2 domain models and enums representing anonymized incident patterns, privacy sanitization levels,
cryptographic signatures, exported/imported knowledge bundles, import validation results, and subsystem statistics.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SanitizationLevel(str, Enum):
    """Level of privacy scrubbing applied to exported incident data."""

    STRICT = "STRICT"
    AGGRESSIVE = "AGGRESSIVE"
    STANDARD = "STANDARD"


class BundleType(str, Enum):
    """Taxonomy of offline federated knowledge bundle."""

    INCIDENT_PATTERN_BUNDLE = "INCIDENT_PATTERN_BUNDLE"
    REMEDIATION_RUNBOOK_BUNDLE = "REMEDIATION_RUNBOOK_BUNDLE"
    FULL_FEDERATED_KNOWLEDGE = "FULL_FEDERATED_KNOWLEDGE"


class SignatureAlgorithm(str, Enum):
    """Cryptographic signature algorithm."""

    HMAC_SHA256 = "HMAC_SHA256"
    RSA_SHA256 = "RSA_SHA256"
    ECDSA_SHA256 = "ECDSA_SHA256"


class ExportStatus(str, Enum):
    """Export operation outcome status."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class ImportStatus(str, Enum):
    """Import validation and ingestion status."""

    VALIDATED_AND_IMPORTED = "VALIDATED_AND_IMPORTED"
    SIGNATURE_VERIFICATION_FAILED = "SIGNATURE_VERIFICATION_FAILED"
    PRIVACY_CHECK_FAILED = "PRIVACY_CHECK_FAILED"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    REJECTED = "REJECTED"


class TrustOrigin(str, Enum):
    """Trust classification origin of imported knowledge."""

    INTERNAL_SITE = "INTERNAL_SITE"
    FEDERATED_SITE_ALPHA = "FEDERATED_SITE_ALPHA"
    FEDERATED_SITE_BETA = "FEDERATED_SITE_BETA"
    PARTNER_NOC = "PARTNER_NOC"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------


class AnonymizedPattern(BaseModel):
    """Anonymized structural incident pattern stripped of environment-specific PII/IPs."""

    model_config = ConfigDict(frozen=False)

    pattern_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: str = Field(...)
    symptoms: List[str] = Field(default_factory=list)
    structural_signals: List[str] = Field(default_factory=list)
    root_cause_hypothesis: str = Field(...)
    recommended_action: str = Field(...)
    confidence_score: float = Field(default=0.90, ge=0.0, le=1.0)
    anonymized_metadata: Dict[str, Any] = Field(default_factory=dict)


class SanitizedIncident(BaseModel):
    """Incident record scrubbed of all raw telemetry, IP addresses, credentials, and topology secrets."""

    model_config = ConfigDict(frozen=False)

    incident_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    abstract_severity: str = Field(default="HIGH")
    anonymized_pattern: AnonymizedPattern = Field(...)
    sanitized_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sanitization_level: SanitizationLevel = Field(default=SanitizationLevel.STRICT)


class BundleSignature(BaseModel):
    """Cryptographic signature envelope verifying bundle authenticity and integrity."""

    model_config = ConfigDict(frozen=False)

    signer_id: str = Field(...)
    algorithm: SignatureAlgorithm = Field(default=SignatureAlgorithm.HMAC_SHA256)
    signature_hex: str = Field(...)
    signed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    public_key_fingerprint: str = Field(default="")


class FederatedKnowledgeBundle(BaseModel):
    """Complete air-gapped export/import knowledge payload containing signed anonymized patterns."""

    model_config = ConfigDict(frozen=False)

    bundle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bundle_type: BundleType = Field(default=BundleType.INCIDENT_PATTERN_BUNDLE)
    source_site_id: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sanitized_incidents: List[SanitizedIncident] = Field(default_factory=list)
    signature: BundleSignature = Field(...)
    schema_version: str = Field(default="1.0.0")


class ImportValidationResult(BaseModel):
    """Validation report evaluated prior to importing external bundle into local RAG/VectorStore."""

    model_config = ConfigDict(frozen=False)

    validation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bundle_id: str = Field(...)
    status: ImportStatus = Field(default=ImportStatus.REJECTED)
    signature_valid: bool = Field(default=False)
    privacy_valid: bool = Field(default=False)
    schema_valid: bool = Field(default=False)
    patterns_imported_count: int = Field(default=0)
    messages: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExportBundleResult(BaseModel):
    """Result payload produced when exporting anonymized incident intelligence."""

    model_config = ConfigDict(frozen=False)

    export_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bundle: Optional[FederatedKnowledgeBundle] = Field(default=None)
    status: ExportStatus = Field(default=ExportStatus.COMPLETED)
    bundle_file_path: str = Field(default="")
    total_patterns_exported: int = Field(default=0)
    signature_fingerprint: str = Field(default="")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FederatedIntelligenceStatistics(BaseModel):
    """Subsystem execution metrics and RAG index statistics."""

    model_config = ConfigDict(frozen=False)

    total_bundles_exported: int = Field(default=0)
    total_bundles_imported: int = Field(default=0)
    total_federated_patterns_indexed: int = Field(default=0)
    signature_failures: int = Field(default=0)
    privacy_violations_blocked: int = Field(default=0)
    local_rag_matches: int = Field(default=0)
