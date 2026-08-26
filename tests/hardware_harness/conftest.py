"""
Pytest configuration and fixtures for the Virtual Hardware Integration Test Harness.
"""

from typing import Generator
import pytest

from agents.failover.production_models import DeviceEndpointProfile
from tests.hardware_harness.virtual_device_manager import VirtualDeviceManager


@pytest.fixture
def vdm() -> Generator[VirtualDeviceManager, None, None]:
    """Provides an isolated VirtualDeviceManager and cleans up after test."""
    manager = VirtualDeviceManager()
    yield manager
    manager.cleanup()


@pytest.fixture
def frr_profile(vdm: VirtualDeviceManager) -> DeviceEndpointProfile:
    return vdm.create_endpoint_profile("frr-router-01")


@pytest.fixture
def ceos_profile(vdm: VirtualDeviceManager) -> DeviceEndpointProfile:
    return vdm.create_endpoint_profile("arista-ceos-01")


@pytest.fixture
def cisco_profile(vdm: VirtualDeviceManager) -> DeviceEndpointProfile:
    return vdm.create_endpoint_profile("cisco-c8k-01")


@pytest.fixture
def sonic_profile(vdm: VirtualDeviceManager) -> DeviceEndpointProfile:
    return vdm.create_endpoint_profile("sonic-leaf-01")
