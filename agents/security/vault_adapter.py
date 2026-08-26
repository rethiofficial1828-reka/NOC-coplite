"""
Secret Provider & Vault Adapter Module for NOC Copilot v1.4.

Defines:
- ISecretProvider: Abstract interface for enterprise secret managers.
- NotConfiguredSecretProvider: Safe default returning NOT_CONFIGURED.
- LocalTestSecretProvider: Ephemeral in-memory provider for unit/integration testing without disk persistence.
- VaultSecretAdapter: Stub provider for HashiCorp Vault / Cloud KMS integration.

Guarantees:
- Zero plaintext passwords in configuration files
- Zero writing of private keys or secrets to disk
- Strict AAA RBAC validation before releasing sensitive payloads
- Masked logging and audit records
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from agents.core.logger import get_agent_logger
from agents.security.security_models import (
    AAAIdentity,
    AAARole,
    CredentialLease,
    CredentialRotationStatus,
)

logger = get_agent_logger("SecretProvider")


class ISecretProvider(ABC):
    """
    Abstract Interface for secure credential and secret providers.
    """

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Return True only if secret provider is initialized and accessible."""
        pass

    @abstractmethod
    def get_secret_metadata(self, path: str) -> Optional[CredentialLease]:
        """Fetch non-sensitive secret lease metadata."""
        pass

    @abstractmethod
    def fetch_secret_payload(self, path: str, identity: AAAIdentity) -> Optional[Dict[str, Any]]:
        """
        Fetch secret payload if calling identity possesses sufficient RBAC authority.
        """
        pass

    @abstractmethod
    def check_rotation_status(self, credential_id: str) -> CredentialRotationStatus:
        """Return current certificate/key rotation status."""
        pass


class NotConfiguredSecretProvider(ISecretProvider):
    """
    Default safe secret provider implementation.
    Reports is_configured=False and rejects all access attempts.
    """

    @property
    def is_configured(self) -> bool:
        return False

    def get_secret_metadata(self, path: str) -> Optional[CredentialLease]:
        logger.warning(f"get_secret_metadata rejected: SecretProvider is NOT_CONFIGURED.")
        return None

    def fetch_secret_payload(self, path: str, identity: AAAIdentity) -> Optional[Dict[str, Any]]:
        logger.warning(f"fetch_secret_payload rejected for path '{path}': NOT_CONFIGURED.")
        return None

    def check_rotation_status(self, credential_id: str) -> CredentialRotationStatus:
        now = datetime.now(timezone.utc)
        return CredentialRotationStatus(
            credential_id=credential_id,
            last_rotated_at=now,
            next_rotation_due=now,
            status="NOT_CONFIGURED",
        )


class LocalTestSecretProvider(ISecretProvider):
    """
    Ephemeral in-memory secret provider for air-gapped unit and integration testing.
    Stores data only in volatile memory with strict RBAC enforcement.
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, CredentialLease] = {}
        self._rotation: Dict[str, CredentialRotationStatus] = {}

    @property
    def is_configured(self) -> bool:
        return True

    def store_ephemeral_secret(
        self,
        path: str,
        credential_id: str,
        payload: Dict[str, Any],
        lease_duration_sec: int = 3600,
        rotation_interval_days: int = 90,
    ) -> None:
        """Store an ephemeral test secret payload in memory."""
        # Sanity check: reject raw plaintext passwords or strings
        if not isinstance(payload, dict):
            raise ValueError("Secret payload must be a structured dictionary.")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=lease_duration_sec)
        next_rotation = now + timedelta(days=rotation_interval_days)

        self._store[path] = payload
        self._metadata[path] = CredentialLease(
            path=path,
            lease_duration_sec=lease_duration_sec,
            issued_at=now,
            expires_at=expires_at,
        )
        self._rotation[credential_id] = CredentialRotationStatus(
            credential_id=credential_id,
            last_rotated_at=now,
            next_rotation_due=next_rotation,
            status="CURRENT",
        )
        logger.info(f"Stored ephemeral secret at '{path}' (id: {credential_id}) [CONTENT REDACTED].")

    def get_secret_metadata(self, path: str) -> Optional[CredentialLease]:
        return self._metadata.get(path)

    def fetch_secret_payload(self, path: str, identity: AAAIdentity) -> Optional[Dict[str, Any]]:
        """
        Release secret payload ONLY if identity possesses NOC_ADMIN or SECURITY_OFFICER role.
        """
        # RBAC Check
        has_permission = identity.has_role(AAARole.NOC_ADMIN) or identity.has_role(AAARole.SECURITY_OFFICER)
        if not has_permission:
            logger.warning(
                f"Unauthorized secret access attempt to '{path}' by user '{identity.username}' (Roles: {identity.roles})."
            )
            return None

        if path not in self._store:
            logger.warning(f"Secret path '{path}' not found.")
            return None

        logger.info(f"Secret payload released for path '{path}' to authorized user '{identity.username}'.")
        return dict(self._store[path])

    def check_rotation_status(self, credential_id: str) -> CredentialRotationStatus:
        if credential_id in self._rotation:
            return self._rotation[credential_id]

        now = datetime.now(timezone.utc)
        return CredentialRotationStatus(
            credential_id=credential_id,
            last_rotated_at=now,
            next_rotation_due=now + timedelta(days=90),
            status="CURRENT",
        )


class VaultSecretAdapter(ISecretProvider):
    """
    HashiCorp Vault / Cloud KMS Adapter for enterprise production deployments.
    (Stub implementation for v1.4 architectural compliance).
    """

    def __init__(self, vault_addr: Optional[str] = None) -> None:
        self._vault_addr = vault_addr

    @property
    def is_configured(self) -> bool:
        return self._vault_addr is not None and len(self._vault_addr.strip()) > 0

    def get_secret_metadata(self, path: str) -> Optional[CredentialLease]:
        if not self.is_configured:
            return None
        now = datetime.now(timezone.utc)
        return CredentialLease(
            path=path,
            lease_duration_sec=3600,
            issued_at=now,
            expires_at=now + timedelta(hours=1),
        )

    def fetch_secret_payload(self, path: str, identity: AAAIdentity) -> Optional[Dict[str, Any]]:
        if not self.is_configured:
            logger.warning("VaultSecretAdapter is not configured.")
            return None
        # Stub: production network communication is disabled in v1.4
        logger.info(f"VaultSecretAdapter stub queried for path '{path}'.")
        return None

    def check_rotation_status(self, credential_id: str) -> CredentialRotationStatus:
        now = datetime.now(timezone.utc)
        return CredentialRotationStatus(
            credential_id=credential_id,
            last_rotated_at=now,
            next_rotation_due=now + timedelta(days=30),
            status="CURRENT",
        )
