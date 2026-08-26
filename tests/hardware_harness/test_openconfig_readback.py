"""
Harness Qualification Tests: Cross-Protocol Consistency & OpenConfig Readback.

Tests:
1. gNMI and NETCONF cross-protocol normalization
2. Verification of semantic equivalence across transport protocols
3. Multi-leaf OpenConfig state normalization
"""

import pytest

from agents.failover import (
    DeviceEndpointProfile,
    GNMIControlPlane,
    NETCONFControlPlane,
    TransportProtocol,
)
from tests.hardware_harness.harness_models import ReadbackVerificationResult


def test_cross_protocol_semantic_equivalence(
    frr_profile: DeviceEndpointProfile,
    cisco_profile: DeviceEndpointProfile,
):
    """
    Verify that reading OpenConfig operational data over gNMI and NETCONF
    produces semantically equivalent normalized data models.
    """
    # 1. Read via gNMI
    gnmi_driver = GNMIControlPlane(declared_allowlist={frr_profile.device_id})
    gnmi_driver.connect_mtls(frr_profile)
    gnmi_if = gnmi_driver.get_interface_state(frr_profile.device_id, "eth1")
    gnmi_route = gnmi_driver.get_static_default_route(frr_profile.device_id)
    gnmi_bfd = gnmi_driver.get_bfd_peer_state(frr_profile.device_id, "eth1", "10.10.1.1")

    gnmi_res = ReadbackVerificationResult(
        device_id=frr_profile.device_id,
        protocol=TransportProtocol.GNMI_GRPC,
        interface_state=gnmi_if,
        default_route=gnmi_route,
        bfd_state=gnmi_bfd,
    )

    # 2. Read via NETCONF
    netconf_driver = NETCONFControlPlane(declared_allowlist={cisco_profile.device_id})
    netconf_driver.connect_mtls(cisco_profile)
    nc_if = netconf_driver.get_interface_state(cisco_profile.device_id, "eth1")
    nc_route = netconf_driver.get_static_default_route(cisco_profile.device_id)
    nc_bfd = netconf_driver.get_bfd_peer_state(cisco_profile.device_id, "eth1", "10.10.1.1")

    nc_res = ReadbackVerificationResult(
        device_id=cisco_profile.device_id,
        protocol=TransportProtocol.NETCONF_YANG,
        interface_state=nc_if,
        default_route=nc_route,
        bfd_state=nc_bfd,
    )

    # 3. Verify semantic equivalence
    assert gnmi_res.interface_state.admin_status == nc_res.interface_state.admin_status
    assert gnmi_res.interface_state.oper_status == nc_res.interface_state.oper_status
    assert gnmi_res.default_route.prefix == nc_res.default_route.prefix
    assert gnmi_res.default_route.next_hop == nc_res.default_route.next_hop
    assert gnmi_res.bfd_state.local_state == nc_res.bfd_state.local_state
    assert gnmi_res.bfd_state.remote_state == nc_res.bfd_state.remote_state
