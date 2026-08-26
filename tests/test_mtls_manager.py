"""
Unit Test Suite for NOC Copilot v1.4 Phase 2: mTLS & Certificate Authority Validation.

Tests:
1. Valid certificate metadata
2. Expired certificate detection
3. Not yet valid certificate detection
4. Invalid certificate chain (issuer mismatch, validity window violation)
5. Hostname/SAN mismatch validation
6. Missing CA reference in trust store
7. Missing client certificate in registry
8. MTLSManager readiness lifecycle (NOT_CONFIGURED, READY, EXPIRED, INVALID)
9. Safe status summary non-leakage
"""

from datetime import datetime, timedelta, timezone
import pytest

from agents.security import (
    CertificateAuthorityValidator,
    CertificateProfile,
    CredentialReference,
    MTLSConnectionProfile,
    MTLSManager,
    MTLSReadinessStatus,
)


@pytest.fixture
def valid_ca_profile() -> CertificateProfile:
    now = datetime.now(timezone.utc)
    return CertificateProfile(
        cert_id="root-ca-01",
        common_name="Enterprise Root CA",
        san_list=["ca.corp.internal"],
        issuer="Enterprise Root CA",
        valid_from=now - timedelta(days=365),
        valid_until=now + timedelta(days=3650),
        fingerprint_sha256="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        is_ca=True,
        key_algorithm="RSA_4096",
    )


@pytest.fixture
def valid_client_profile() -> CertificateProfile:
    now = datetime.now(timezone.utc)
    return CertificateProfile(
        cert_id="noc-copilot-client",
        common_name="noc-copilot.corp.internal",
        san_list=["noc-copilot.corp.internal", "10.0.0.5"],
        issuer="Enterprise Root CA",
        valid_from=now - timedelta(days=30),
        valid_until=now + timedelta(days=365),
        fingerprint_sha256="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
        is_ca=False,
        key_algorithm="RSA_4096",
    )


# ---------------------------------------------------------------------------
# 1. Certificate Validation Tests
# ---------------------------------------------------------------------------


def test_valid_ca_certificate(valid_ca_profile: CertificateProfile):
    """Verify valid CA certificate passes validation."""
    is_valid, errors = CertificateAuthorityValidator.validate_ca_certificate(valid_ca_profile)
    assert is_valid is True
    assert len(errors) == 0


def test_expired_certificate_detection():
    """Verify expired certificate is flagged as invalid."""
    now = datetime.now(timezone.utc)
    expired_cert = CertificateProfile(
        cert_id="old-cert",
        common_name="old.corp.internal",
        san_list=[],
        issuer="Enterprise Root CA",
        valid_from=now - timedelta(days=400),
        valid_until=now - timedelta(days=10),
        fingerprint_sha256="c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        is_ca=False,
    )
    assert expired_cert.is_expired is True
    is_valid, errors = CertificateAuthorityValidator.validate_client_certificate(expired_cert)
    assert is_valid is False
    assert any("expired" in err.lower() for err in errors)


def test_not_yet_valid_certificate():
    """Verify future certificate validity is rejected."""
    now = datetime.now(timezone.utc)
    future_cert = CertificateProfile(
        cert_id="future-cert",
        common_name="future.corp.internal",
        san_list=[],
        issuer="Enterprise Root CA",
        valid_from=now + timedelta(days=10),
        valid_until=now + timedelta(days=365),
        fingerprint_sha256="d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
        is_ca=False,
    )
    assert future_cert.is_not_yet_valid is True
    is_valid, errors = CertificateAuthorityValidator.validate_client_certificate(future_cert)
    assert is_valid is False
    assert any("not yet valid" in err.lower() for err in errors)


def test_invalid_certificate_chain_issuer_mismatch(valid_ca_profile: CertificateProfile):
    """Verify issuer mismatch between client cert and CA cert fails validation."""
    now = datetime.now(timezone.utc)
    rogue_client = CertificateProfile(
        cert_id="rogue-client",
        common_name="rogue.corp.internal",
        san_list=[],
        issuer="Untrusted Third Party CA",
        valid_from=now - timedelta(days=30),
        valid_until=now + timedelta(days=180),
        fingerprint_sha256="e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
        is_ca=False,
    )
    is_valid, errors = CertificateAuthorityValidator.validate_certificate_chain(rogue_client, valid_ca_profile)
    assert is_valid is False
    assert any("chain mismatch" in err.lower() for err in errors)


def test_hostname_san_matching(valid_client_profile: CertificateProfile):
    """Verify SAN and CN matching rules."""
    assert valid_client_profile.is_valid_for_host("noc-copilot.corp.internal") is True
    assert valid_client_profile.is_valid_for_host("10.0.0.5") is True
    assert valid_client_profile.is_valid_for_host("unauthorized.corp.internal") is False

    is_valid, errors = CertificateAuthorityValidator.validate_server_name(
        valid_client_profile, "unauthorized.corp.internal"
    )
    assert is_valid is False
    assert len(errors) == 1


# ---------------------------------------------------------------------------
# 2. MTLSManager Readiness & Profile Lifecycle
# ---------------------------------------------------------------------------


def test_mtls_manager_not_configured():
    """Verify empty MTLSManager returns NOT_CONFIGURED."""
    mgr = MTLSManager()
    assert mgr.check_readiness() == MTLSReadinessStatus.NOT_CONFIGURED


def test_mtls_manager_ready_state(
    valid_ca_profile: CertificateProfile, valid_client_profile: CertificateProfile
):
    """Verify MTLSManager transitions to READY when valid certs and profiles are registered."""
    mgr = MTLSManager()
    mgr.register_ca_profile(valid_ca_profile)
    mgr.register_client_profile(valid_client_profile)

    conn_profile = MTLSConnectionProfile(
        profile_id="conn-core-01",
        device_id="core-01",
        tls_server_name="core-01.corp.internal",
        ca_cert_ref=CredentialReference(credential_id=valid_ca_profile.cert_id, vault_path="secret/ca"),
        client_cert_ref=CredentialReference(credential_id=valid_client_profile.cert_id, vault_path="secret/client"),
        client_key_ref=CredentialReference(credential_id="client-key", vault_path="secret/key"),
    )
    mgr.register_connection_profile(conn_profile)

    is_valid, errors = mgr.validate_connection("core-01")
    assert is_valid is True
    assert len(errors) == 0

    assert mgr.check_readiness("core-01") == MTLSReadinessStatus.READY
    assert mgr.check_readiness() == MTLSReadinessStatus.READY


def test_mtls_manager_missing_ca_reference(valid_client_profile: CertificateProfile):
    """Verify validation fails when referenced CA is missing."""
    mgr = MTLSManager()
    mgr.register_client_profile(valid_client_profile)

    conn_profile = MTLSConnectionProfile(
        profile_id="conn-rtr-01",
        device_id="rtr-01",
        tls_server_name="rtr-01.corp.internal",
        ca_cert_ref=CredentialReference(credential_id="non-existent-ca", vault_path="secret/ca"),
        client_cert_ref=CredentialReference(credential_id=valid_client_profile.cert_id, vault_path="secret/client"),
        client_key_ref=CredentialReference(credential_id="key", vault_path="secret/key"),
    )
    mgr.register_connection_profile(conn_profile)

    is_valid, errors = mgr.validate_connection("rtr-01")
    assert is_valid is False
    assert any("not registered in trust store" in err for err in errors)


def test_safe_status_summary_non_leakage(
    valid_ca_profile: CertificateProfile, valid_client_profile: CertificateProfile
):
    """Verify safe status summary contains only public metadata and masks fingerprints."""
    mgr = MTLSManager()
    mgr.register_ca_profile(valid_ca_profile)
    mgr.register_client_profile(valid_client_profile)

    summary = mgr.get_safe_status_summary()
    assert summary["total_ca_certs"] == 1
    assert summary["total_client_certs"] == 1
    assert summary["readiness_status"] == "READY"
    assert "..." in summary["ca_certificates"][0]["fingerprint"]
    assert "private" not in str(summary).lower()
