"""
Harness Qualification Tests: NETCONF Driver over Virtual Network Operating Systems.

Tests:
1. NETCONF driver session establishment with virtual NOS profile
2. Capability discovery (Read ENABLED, Mutation DISABLED)
3. Structured YANG/XML Get for interfaces and routes
4. BFD state query
5. Zero CLI/SSH command execution verification
"""

import pytest

from agents.failover import (
    ControlPlaneStatus,
    DeviceEndpointProfile,
    NETCONFControlPlane,
    OC_STATIC_DEFAULT_ROUTE,
)


def test_netconf_qualification_on_cisco_profile(cisco_profile: DeviceEndpointProfile):
    """Verify NETCONF driver connects to Cisco profile via mTLS/SSH transport."""
    driver = NETCONFControlPlane(declared_allowlist={cisco_profile.device_id})
    connected = driver.connect_mtls(cisco_profile)
    assert connected is True
    assert driver.is_configured is True

    readiness = driver.check_readiness()
    assert readiness.success is True
    assert readiness.status == ControlPlaneStatus.READY
    assert readiness.details["transport_type"] == "NETCONF_YANG"
    assert readiness.details["read_capability"] == "ENABLED"
    assert readiness.details["mutation_capability"] == "DISABLED"


def test_netconf_read_interface_and_route_state(cisco_profile: DeviceEndpointProfile):
    """Verify reading interface and route operational state over structured NETCONF."""
    driver = NETCONFControlPlane(declared_allowlist={cisco_profile.device_id})
    driver.connect_mtls(cisco_profile)

    if_state = driver.get_interface_state(cisco_profile.device_id, "eth1")
    assert if_state is not None
    assert if_state.admin_status == "UP"
    assert if_state.oper_status == "UP"

    route = driver.get_static_default_route(cisco_profile.device_id)
    assert route is not None
    assert route.prefix == "0.0.0.0/0"
    assert route.next_hop == "10.10.1.1"


def test_netconf_read_bfd_state(cisco_profile: DeviceEndpointProfile):
    """Verify reading BFD state over structured NETCONF RPC."""
    driver = NETCONFControlPlane(declared_allowlist={cisco_profile.device_id})
    driver.connect_mtls(cisco_profile)

    bfd = driver.get_bfd_peer_state(cisco_profile.device_id, "eth1", "10.10.1.1")
    assert bfd is not None
    assert bfd.local_state.value == "UP"
    assert bfd.remote_state.value == "UP"
