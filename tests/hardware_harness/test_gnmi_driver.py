"""
Harness Qualification Tests: gNMI Driver over Virtual Network Operating Systems.

Tests:
1. Virtual NOS discovery & availability detection
2. gNMI mTLS session connection with virtual NOS profile
3. Capability discovery (Read ENABLED, Mutation DISABLED)
4. OpenConfig Get for interface state & config
5. OpenConfig Get for static routing & next-hop
6. OpenConfig Get for BFD telemetry state
"""

import pytest

from agents.failover import (
    ControlPlaneStatus,
    DeviceEndpointProfile,
    GNMIControlPlane,
    OC_INTERFACE_CONFIG,
    OC_NEXT_HOP,
    OC_STATIC_ROUTE_METRIC,
)
from tests.hardware_harness.virtual_device_manager import VirtualDeviceManager


def test_virtual_nos_inventory_discovery(vdm: VirtualDeviceManager):
    """Verify virtual NOS targets are discovered and availability is reported accurately."""
    devices = vdm.list_devices()
    assert len(devices) >= 4

    frr_spec = vdm.get_device("frr-router-01")
    assert frr_spec is not None
    # frrouting/frr image is present locally
    assert frr_spec.is_image_available is True

    ceos_spec = vdm.get_device("arista-ceos-01")
    assert ceos_spec is not None
    # explicitly report availability state without faking live presence
    assert ceos_spec.is_image_available is False


def test_gnmi_qualification_on_frr(frr_profile: DeviceEndpointProfile):
    """Verify gNMI driver connects to qualified FRR virtual device via mTLS profile."""
    driver = GNMIControlPlane(declared_allowlist={frr_profile.device_id})
    connected = driver.connect_mtls(frr_profile)
    assert connected is True
    assert driver.is_configured is True

    readiness = driver.check_readiness()
    assert readiness.success is True
    assert readiness.status == ControlPlaneStatus.READY
    assert readiness.details["read_capability"] == "ENABLED"
    assert readiness.details["mutation_capability"] == "DISABLED"


def test_gnmi_read_openconfig_interface_hierarchy(frr_profile: DeviceEndpointProfile):
    """Verify structured OpenConfig interface state and config readback."""
    driver = GNMIControlPlane(declared_allowlist={frr_profile.device_id})
    driver.connect_mtls(frr_profile)

    # 1. State
    st = driver.get_interface_state(frr_profile.device_id, "eth1")
    assert st is not None
    assert st.admin_status == "UP"
    assert st.oper_status == "UP"

    # 2. Config
    cfg = driver.read_openconfig_state(
        frr_profile.device_id,
        OC_INTERFACE_CONFIG.format(name="eth1"),
    )
    assert isinstance(cfg, dict)


def test_gnmi_read_openconfig_routing_hierarchy(frr_profile: DeviceEndpointProfile):
    """Verify structured OpenConfig default route, next-hop, and metric readback."""
    driver = GNMIControlPlane(declared_allowlist={frr_profile.device_id})
    driver.connect_mtls(frr_profile)

    route = driver.get_static_default_route(frr_profile.device_id)
    assert route is not None
    assert route.prefix == "0.0.0.0/0"
    assert route.next_hop == "10.10.1.1"
    assert route.metric == 10

    # Read metric leaf specifically
    metric_data = driver.read_openconfig_state(
        frr_profile.device_id,
        OC_STATIC_ROUTE_METRIC.format(index="1"),
    )
    assert isinstance(metric_data, dict)

    # Read next-hop leaf specifically
    nh_data = driver.read_openconfig_state(
        frr_profile.device_id,
        OC_NEXT_HOP.format(index="1"),
    )
    assert isinstance(nh_data, dict)


def test_gnmi_read_openconfig_bfd_hierarchy(frr_profile: DeviceEndpointProfile):
    """Verify structured OpenConfig BFD peer state readback."""
    driver = GNMIControlPlane(declared_allowlist={frr_profile.device_id})
    driver.connect_mtls(frr_profile)

    bfd = driver.get_bfd_peer_state(frr_profile.device_id, "eth1", "10.10.1.1")
    assert bfd is not None
    assert bfd.local_state.value == "UP"
    assert bfd.remote_state.value == "UP"
    assert bfd.detection_time_ms == 50.0
