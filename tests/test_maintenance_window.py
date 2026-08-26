"""
Unit Test Suite for NOC Copilot v1.4 Phase 5: Maintenance Window & Change Governance.

Tests:
1. MaintenanceWindow active window evaluation against UTC timestamps
2. Rejection of changes outside scheduled UTC start/end window
3. Device allowlist scoping inside change window
4. NotConfiguredChangeWindowProvider safe default failure
5. TestChangeWindowProvider registration and query lifecycle
"""

from datetime import datetime, timedelta, timezone
import pytest

from agents.failover import (
    MaintenanceWindow,
    NotConfiguredChangeWindowProvider,
    TestChangeWindowProvider,
)


def test_maintenance_window_active_evaluation():
    """Verify window.is_active accurately evaluates current UTC time."""
    now = datetime.now(timezone.utc)
    active_win = MaintenanceWindow(
        change_ticket_id="CHG-1001",
        start_time=now - timedelta(minutes=30),
        end_time=now + timedelta(minutes=30),
        target_devices=["core-01", "rtr-01"],
        approved_by="CAB_APPROVER",
    )
    assert active_win.is_active(now) is True

    past_win = MaintenanceWindow(
        change_ticket_id="CHG-1002",
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(hours=1),
        target_devices=["core-01"],
        approved_by="CAB_APPROVER",
    )
    assert past_win.is_active(now) is False

    future_win = MaintenanceWindow(
        change_ticket_id="CHG-1003",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=2),
        target_devices=["core-01"],
        approved_by="CAB_APPROVER",
    )
    assert future_win.is_active(now) is False


def test_not_configured_provider_fails_closed():
    """Verify NotConfiguredChangeWindowProvider safely blocks execution."""
    provider = NotConfiguredChangeWindowProvider()
    assert provider.get_active_window("core-01") is None
    ok, msg = provider.validate_change_window("core-01")
    assert ok is False
    assert "NOT_CONFIGURED" in msg


def test_test_change_window_provider_flow():
    """Verify TestChangeWindowProvider detects valid and invalid device scopes."""
    now = datetime.now(timezone.utc)
    provider = TestChangeWindowProvider()

    win = MaintenanceWindow(
        change_ticket_id="CHG-5500",
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
        target_devices=["core-01"],
        approved_by="CAB_APPROVER",
    )
    provider.register_window(win)

    # Allowlisted device in window
    ok, msg = provider.validate_change_window("core-01", now=now)
    assert ok is True
    assert "CHG-5500" in msg

    # Unallowlisted device outside window
    ok_other, msg_other = provider.validate_change_window("core-99", now=now)
    assert ok_other is False
    assert "No active maintenance window" in msg_other
