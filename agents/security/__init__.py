"""
Security Package Initialization for NOC Copilot v1.4.

Exports:
- AAA roles and identity models (AAARole, AAAIdentity, AuthorizationDecision)
- Certificate and mTLS models (CertificateProfile, MTLSConnectionProfile, CredentialReference, MTLSReadinessStatus)
- Credential lease and rotation models (CredentialLease, CredentialRotationStatus)
- mTLS Validator & Manager (CertificateAuthorityValidator, MTLSManager)
- Secret Providers (ISecretProvider, NotConfiguredSecretProvider, LocalTestSecretProvider, VaultSecretAdapter)
- AAA Service (AAAAuthorizationService, ACTION_PERMISSIONS)
"""

from agents.security.aaa_service import (
    ACTION_PERMISSIONS,
    AAAAuthorizationService,
)
from agents.security.mtls_manager import (
    CertificateAuthorityValidator,
    MTLSManager,
)
from agents.security.security_models import (
    AAAIdentity,
    AAARole,
    AuthorizationDecision,
    CertificateProfile,
    CredentialLease,
    CredentialReference,
    CredentialRotationStatus,
    MTLSConnectionProfile,
    MTLSReadinessStatus,
)
from agents.security.vault_adapter import (
    ISecretProvider,
    LocalTestSecretProvider,
    NotConfiguredSecretProvider,
    VaultSecretAdapter,
)

__all__ = [
    "AAARole",
    "AAAIdentity",
    "AuthorizationDecision",
    "CertificateProfile",
    "MTLSConnectionProfile",
    "CredentialReference",
    "CredentialLease",
    "CredentialRotationStatus",
    "MTLSReadinessStatus",
    "CertificateAuthorityValidator",
    "MTLSManager",
    "ISecretProvider",
    "NotConfiguredSecretProvider",
    "LocalTestSecretProvider",
    "VaultSecretAdapter",
    "AAAAuthorizationService",
    "ACTION_PERMISSIONS",
]
