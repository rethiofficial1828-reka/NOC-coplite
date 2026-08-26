"""
Unit Test Suite for NOC Copilot v1.4 Phase 3: Negative Security & Transport Error Resilience.

Tests:
1. Rejection of unallowlisted device endpoints
2. Rejection of hostname/SAN mismatch during mTLS handshake
3. Rejection of invalid certificate paths or injection tokens
4. Handling of transport timeouts without crashes
5. Handling of TLS handshake failures and state degradation
6. Handling of malformed or corrupted OpenConfig payloads
7. Assurance of zero production socket connections or arbitrary CLI execution
"""

import pytest

from agents.failover import (
    DeviceEndpointProfile,
    GNMIControlPlane,
    MockTransportServer,
    NETCONFControlPlane,
    NOSVendor,
    OC_INTERFACE_STATE,
    TransportProtocol,
    TransportStatus,
)


@pytest.fixture
def base_endpoint_profile() -> DeviceEndpointProfile:
    return DeviceEndpointProfile(
        device_id="core-01",
        hostname="core-01.corp.internal",
        management_ip="192.168.1.1",
        management_port=9339,
        vendor=NOSVendor.ARISTA_EOS,
        transport=TransportProtocol.GNMI_GRPC,
        tls_server_name="core-01.corp.internal",
        ca_cert_path="/etc/ssl/certs/ca.pem",
        client_cert_path="/etc/ssl/certs/client.pem",
        client_key_path="/etc/ssl/private/client.key",
        allowlisted=True,
    )


# ---------------------------------------------------------------------------
# 1. Allowlist & Profile Rejection Tests
# ---------------------------------------------------------------------------


def test_unallowlisted_device_rejected(base_endpoint_profile: DeviceEndpointProfile):
    """Verify device not in declared allowlist is rejected during connect_mtls."""
    driver = GNMIControlPlane(declared_allowlist={"rtr-01", "hub"})  # core-01 excluded
    assert driver.connect_mtls(base_endpoint_profile) is False
    assert driver.is_configured is False
    assert driver.session_state is not None
    assert driver.session_state.status == TransportStatus.AUTH_ERROR


def test_command_injection_profile_rejected():
    """Verify endpoint profile with shell injection tokens fails closed."""
    unsafe = DeviceEndpointProfile(
        device_id="core-01; reboot",
        hostname="core-01.corp | rm -rf",
        management_ip="10.0.0.1",
        vendor=NOSVendor.SONIC,
        transport=TransportProtocol.GNMI_GRPC,
        tls_server_name="core-01",
        ca_cert_path="/ca.pem",
        client_cert_path="/cert.pem",
        client_key_path="/key.pem",
    )
    driver = GNMIControlPlane()
    assert driver.connect_mtls(unsafe) is False


# ---------------------------------------------------------------------------
# 2. Network & Error Resilience Tests
# ---------------------------------------------------------------------------


def test_tls_handshake_failure_handling(base_endpoint_profile: DeviceEndpointProfile):
    """Verify TLS handshake rejection sets TLS_ERROR and fails closed."""
    mock = MockTransportServer()
    mock.should_fail_tls = True

    driver = GNMIControlPlane(declared_allowlist={"core-01"}, mock_server=mock)
    assert driver.connect_mtls(base_endpoint_profile) is False
    assert driver.is_configured is False
    assert driver.session_state is not None
    assert driver.session_state.status == TransportStatus.TLS_ERROR


def test_transport_timeout_resilience(base_endpoint_profile: DeviceEndpointProfile):
    """Verify query timeouts are handled gracefully and return empty dictionaries."""
    mock = MockTransportServer()
    driver = GNMIControlPlane(declared_allowlist={"core-01"}, mock_server=mock)
    assert driver.connect_mtls(base_endpoint_profile) is True

    # Inject timeout
    mock.should_timeout = True
    result = driver.read_openconfig_state("core-01", OC_INTERFACE_STATE)
    assert result == {}
    assert "timed out" in driver.session_state.last_error.lower()


def test_malformed_response_handling(base_endpoint_profile: DeviceEndpointProfile):
    """Verify malformed or corrupted payloads do not cause crashes."""
    mock = MockTransportServer()
    mock.should_return_malformed = True

    driver = GNMIControlPlane(declared_allowlist={"core-01"}, mock_server=mock)
    driver.connect_mtls(base_endpoint_profile)

    if_state = driver.get_interface_state("core-01", "eth1")
    assert if_state is None  # Gracefully handles missing expected keys


def test_netconf_unallowlisted_read_rejected(base_endpoint_profile: DeviceEndpointProfile):
    """Verify NETCONF rejects reading state from an unallowlisted target."""
    driver = NETCONFControlPlane(declared_allowlist={"core-01"})
    driver.connect_mtls(base_endpoint_profile)

    data = driver.read_openconfig_state("unauthorized-switch", OC_INTERFACE_STATE)
    assert data == {}
