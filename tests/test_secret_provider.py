"""
Unit Test Suite for NOC Copilot v1.4 Phase 2: Secret Provider & Credential Management.

Tests:
1. NotConfiguredSecretProvider readiness & safe rejection
2. LocalTestSecretProvider storage & lease metadata
3. Plaintext secret string rejection (must be structured dict)
4. RBAC authorization gate on secret payload retrieval
5. CredentialReference non-leakage in repr and str
6. Credential rotation tracking and due date calculation
7. VaultSecretAdapter stub behavior
"""

from datetime import datetime, timedelta, timezone
import pytest

from agents.security import (
    AAAIdentity,
    AAARole,
    CredentialReference,
    CredentialRotationStatus,
    LocalTestSecretProvider,
    NotConfiguredSecretProvider,
    VaultSecretAdapter,
)


@pytest.fixture
def admin_identity() -> AAAIdentity:
    return AAAIdentity(
        user_id="usr-admin-01",
        username="lead_admin",
        roles=[AAARole.NOC_ADMIN],
    )


@pytest.fixture
def operator_identity() -> AAAIdentity:
    return AAAIdentity(
        user_id="usr-op-01",
        username="junior_op",
        roles=[AAARole.NOC_OPERATOR],
    )


# ---------------------------------------------------------------------------
# 1. NotConfiguredSecretProvider Tests
# ---------------------------------------------------------------------------


def test_not_configured_secret_provider(operator_identity: AAAIdentity):
    """Verify NotConfiguredSecretProvider reports unconfigured and returns None."""
    provider = NotConfiguredSecretProvider()
    assert provider.is_configured is False
    assert provider.get_secret_metadata("secret/path") is None
    assert provider.fetch_secret_payload("secret/path", operator_identity) is None

    rot = provider.check_rotation_status("cred-01")
    assert rot.status == "NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# 2. LocalTestSecretProvider & RBAC Fetch Tests
# ---------------------------------------------------------------------------


def test_local_test_secret_provider_storage_and_metadata():
    """Verify storing ephemeral secret creates valid lease metadata."""
    provider = LocalTestSecretProvider()
    assert provider.is_configured is True

    provider.store_ephemeral_secret(
        path="secret/core-01/key",
        credential_id="core-01-key",
        payload={"key_data": "simulated_private_key_material"},
        lease_duration_sec=7200,
    )

    metadata = provider.get_secret_metadata("secret/core-01/key")
    assert metadata is not None
    assert metadata.path == "secret/core-01/key"
    assert metadata.lease_duration_sec == 7200
    assert metadata.expires_at > metadata.issued_at


def test_plaintext_string_rejection():
    """Verify non-dictionary plaintext payloads are rejected."""
    provider = LocalTestSecretProvider()
    with pytest.raises(ValueError) as exc:
        provider.store_ephemeral_secret(
            path="secret/bad",
            credential_id="bad",
            payload="plaintext_password_string",  # type: ignore
        )
    assert "must be a structured dictionary" in str(exc.value)


def test_rbac_gate_on_secret_retrieval(
    admin_identity: AAAIdentity, operator_identity: AAAIdentity
):
    """Verify only NOC_ADMIN / SECURITY_OFFICER can retrieve secret payloads."""
    provider = LocalTestSecretProvider()
    provider.store_ephemeral_secret(
        path="secret/tls/client-key",
        credential_id="client-key-01",
        payload={"encrypted_key": "dummy_bytes"},
    )

    # Unauthorized operator attempt -> None
    op_res = provider.fetch_secret_payload("secret/tls/client-key", operator_identity)
    assert op_res is None

    # Authorized admin attempt -> Payload
    admin_res = provider.fetch_secret_payload("secret/tls/client-key", admin_identity)
    assert admin_res is not None
    assert admin_res["encrypted_key"] == "dummy_bytes"


def test_credential_reference_redaction():
    """Verify CredentialReference masks secrets in repr and str."""
    ref = CredentialReference(
        credential_id="prod-ca-key",
        credential_type="PRIVATE_KEY",
        vault_path="secret/pki/ca/key",
    )
    rep = repr(ref)
    st = str(ref)

    assert "[SECRET REDACTED]" in rep
    assert "prod-ca-key" in st
    assert "PRIVATE_KEY" in rep


def test_credential_rotation_tracking():
    """Verify credential rotation status and due date calculation."""
    now = datetime.now(timezone.utc)
    current_rot = CredentialRotationStatus(
        credential_id="cert-01",
        last_rotated_at=now - timedelta(days=10),
        next_rotation_due=now + timedelta(days=80),
        status="CURRENT",
    )
    assert current_rot.is_rotation_due is False

    overdue_rot = CredentialRotationStatus(
        credential_id="cert-02",
        last_rotated_at=now - timedelta(days=100),
        next_rotation_due=now - timedelta(days=10),
        status="DUE",
    )
    assert overdue_rot.is_rotation_due is True


def test_vault_secret_adapter_stub(admin_identity: AAAIdentity):
    """Verify VaultSecretAdapter stub behavior."""
    unconfigured = VaultSecretAdapter(vault_addr=None)
    assert unconfigured.is_configured is False

    configured = VaultSecretAdapter(vault_addr="https://vault.corp.internal:8200")
    assert configured.is_configured is True
    assert configured.fetch_secret_payload("secret/test", admin_identity) is None
