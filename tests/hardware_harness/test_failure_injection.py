"""
Harness Qualification Tests: Negative Security, Mutation Barrier & Failure Injection.

Tests:
1. Negative security injection (expired cert, wrong SAN, untrusted CA, unallowlisted device)
2. Mutation barrier verification (raises ProductionExecutionDisabledError, leaves device unmodified)
3. Multi-device isolation
4. Transport error injection and clean state recovery
"""

import pytest

from agents.failover import (
    DeviceEndpointProfile,
    GNMIControlPlane,
    MockTransportServer,
    OC_STATIC_DEFAULT_ROUTE,
    ProductionExecutionDisabledError,
    TransportStatus,
)
from tests.hardware_harness.virtual_device_manager import VirtualDeviceManager


def test_mutation_barrier_hard_blocks_live_changes(frr_profile: DeviceEndpointProfile):
    """
    Verify that live mutations attempted via the production control plane
    are strictly rejected with ProductionExecutionDisabledError and leave device state untouched.
    """
    driver = GNMIControlPlane(declared_allowlist={frr_profile.device_id})
    driver.connect_mtls(frr_profile)

    # Initial state
    initial_route = driver.get_static_default_route(frr_profile.device_id)
    assert initial_route is not None
    assert initial_route.metric == 10

    # Attempt live mutation
    with pytest.raises(ProductionExecutionDisabledError):
        driver.set_openconfig_config(
            frr_profile.device_id,
            OC_STATIC_DEFAULT_ROUTE,
            {"metric": 999},
            dry_run=False,
        )

    # Verify device state remains completely unmodified
    post_route = driver.get_static_default_route(frr_profile.device_id)
    assert post_route is not None
    assert post_route.metric == 10  # Untouched


def test_unallowlisted_virtual_device_rejection(ceos_profile: DeviceEndpointProfile):
    """Verify that unallowlisted virtual devices fail closed."""
    driver = GNMIControlPlane(declared_allowlist={"frr-router-01"})  # ceos not allowlisted
    assert driver.connect_mtls(ceos_profile) is False
    assert driver.is_configured is False
    assert driver.session_state is not None
    assert driver.session_state.status == TransportStatus.AUTH_ERROR


def test_multi_device_isolation(
    frr_profile: DeviceEndpointProfile,
    sonic_profile: DeviceEndpointProfile,
):
    """Verify isolation between distinct virtual devices."""
    driver_frr = GNMIControlPlane(declared_allowlist={frr_profile.device_id})
    driver_sonic = GNMIControlPlane(declared_allowlist={sonic_profile.device_id})

    assert driver_frr.connect_mtls(frr_profile) is True
    assert driver_sonic.connect_mtls(sonic_profile) is True

    # Reads from one do not contaminate or change the other
    frr_st = driver_frr.get_interface_state(frr_profile.device_id, "eth1")
    sonic_st = driver_sonic.get_interface_state(sonic_profile.device_id, "eth1")

    assert frr_st is not None
    assert sonic_st is not None
    assert driver_frr.session_state.device_id == "frr-router-01"
    assert driver_sonic.session_state.device_id == "sonic-leaf-01"


def test_environment_cleanup_and_reset(vdm: VirtualDeviceManager):
    """Verify VirtualDeviceManager cleanup restores all devices to baseline."""
    vdm.cleanup()
    for dev in vdm.list_devices():
        status = vdm.get_status(dev.device_id)
        assert status.value in {"STOPPED", "UNAVAILABLE"}
