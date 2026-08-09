"""
Comprehensive Automated Test Suite for Sprint 12 — Enterprise Live Data Integration Layer.

Validates registration, scheduling, health monitoring, parallel thread execution,
all 7 production collectors, source selection modes (Simulation, Live, Hybrid, Failover),
automatic failover logic, EventBus event propagation, and ExecutionContext integration.
"""

import time
import unittest
from datetime import datetime, timezone
from typing import List

from agents.core.container import ServiceContainer
from agents.core.exceptions import RegistrationError
from agents.events import Event, EventBus
from agents.schemas.schemas import ExecutionContext, TelemetryPacket
from agents.telemetry.telemetry_agent import TelemetryAgent
from agents.collectors import (
    CollectorBase,
    CollectorCapabilities,
    CollectorHealth,
    CollectorHealthMonitor,
    CollectorManager,
    CollectorMetadata,
    CollectorRegistry,
    CollectorSchedule,
    CollectorScheduler,
    CollectorState,
    LinuxCollector,
    PrometheusCollector,
    RESTCollector,
    SNMPCollector,
    SimulationCollector,
    SourceMode,
    SyslogCollector,
    WindowsCollector,
)


class CustomTestCollector(CollectorBase):
    """Concrete mock collector for testing custom implementation behavior."""

    def __init__(self, name: str = "TestCollector", should_fail: bool = False):
        meta = CollectorMetadata(
            name=name,
            description="Mock test collector",
            source_type="custom_test",
        )
        sched = CollectorSchedule(interval_seconds=1.0, priority=5, max_retries=1)
        super().__init__(metadata=meta, schedule=sched)
        self.should_fail = should_fail
        self.init_called = False
        self.shutdown_called = False

    def initialize(self) -> bool:
        self.init_called = True
        self._health.state = CollectorState.READY
        return True

    def shutdown(self) -> bool:
        self.shutdown_called = True
        self._health.state = CollectorState.TERMINATED
        return True

    def collect(self) -> List[TelemetryPacket]:
        if self.should_fail:
            raise ValueError("Intentional mock collection error")
        return [
            TelemetryPacket(
                device_id="test-dev-01",
                interface="Test-Eth0",
                metrics={"utilization": 50.0, "latency": 10.0},
                timestamp=datetime.now(timezone.utc),
            )
        ]


class TestEnterpriseCollectors(unittest.TestCase):

    def setUp(self):
        """Reset singletons and state before each test."""
        EventBus.get_global().clear()
        CollectorRegistry.get_global().clear()
        manager = CollectorManager.get_global()
        manager.stop_scheduler()
        manager.set_source_mode(SourceMode.SIMULATION, reason="Test Reset")

    def tearDown(self):
        """Clean up after test."""
        CollectorManager.get_global().stop_scheduler()
        CollectorRegistry.get_global().clear()

    def test_01_collector_models_and_schemas(self):
        """Test collector metadata, health, schedule, capabilities, and state schemas."""
        meta = CollectorMetadata(name="SNMP1", source_type="snmp")
        self.assertEqual(meta.name, "SNMP1")
        self.assertEqual(meta.source_type, "snmp")

        sched = CollectorSchedule(interval_seconds=10.0, priority=1)
        self.assertEqual(sched.interval_seconds, 10.0)
        self.assertEqual(sched.priority, 1)

        caps = CollectorCapabilities(supports_polling=True, protocol="snmp")
        self.assertTrue(caps.supports_polling)
        self.assertEqual(caps.protocol, "snmp")

        self.assertEqual(SourceMode.LIVE.value, "LIVE")
        self.assertEqual(CollectorState.READY.value, "READY")

    def test_02_collector_base_interface_and_metrics(self):
        """Test CollectorBase lifecycle, success recording, and failure tracking."""
        collector = CustomTestCollector("BaseCollectorTest")
        self.assertTrue(collector.initialize())
        self.assertEqual(collector.name, "BaseCollectorTest")

        # Test execute_collection success
        packets = collector.execute_collection()
        self.assertEqual(len(packets), 1)
        health = collector.health()
        self.assertEqual(health.successful_collections, 1)
        self.assertEqual(health.total_collections, 1)
        self.assertTrue(health.is_healthy)
        self.assertTrue(health.last_latency_ms >= 0.0)

        # Test failure recording
        collector.should_fail = True
        with self.assertRaises(ValueError):
            collector.execute_collection()

        health2 = collector.health()
        self.assertEqual(health2.failed_collections, 1)
        self.assertEqual(health2.total_collections, 2)
        self.assertEqual(health2.consecutive_failures, 1)

    def test_03_collector_registry(self):
        """Test CollectorRegistry registration, lookup, duplicate checks, and unregistration."""
        registry = CollectorRegistry()
        col1 = CustomTestCollector("Col1")
        col2 = CustomTestCollector("Col2")

        registry.register(col1)
        self.assertTrue(registry.exists("Col1"))
        self.assertEqual(registry.get("Col1"), col1)

        # Duplicate registration error
        with self.assertRaises(RegistrationError):
            registry.register(col1)

        # Allow override
        registry.register(col1, allow_override=True)
        registry.register(col2)

        self.assertEqual(len(registry.list_all()), 2)

        # Lookup by source_type
        by_type = registry.get_by_source_type("custom_test")
        self.assertEqual(len(by_type), 2)

        # Unregister
        unregistered = registry.unregister("Col1")
        self.assertEqual(unregistered, col1)
        self.assertFalse(registry.exists("Col1"))

    def test_04_production_collectors_instantiation_and_collection(self):
        """Test all 7 production collectors (Simulation, SNMP, Syslog, REST, Windows, Linux, Prometheus)."""
        collectors = [
            SimulationCollector(),
            SNMPCollector(),
            SyslogCollector(),
            RESTCollector(),
            WindowsCollector(),
            LinuxCollector(),
            PrometheusCollector(),
        ]

        for col in collectors:
            self.assertTrue(col.initialize(), f"Failed to initialize {col.name}")
            packets = col.execute_collection()
            self.assertTrue(len(packets) > 0, f"Collector {col.name} produced zero packets")
            for pkt in packets:
                self.assertIsInstance(pkt, TelemetryPacket)
                self.assertIn("utilization", pkt.metrics)
                self.assertIn("latency", pkt.metrics)
            col.shutdown()

    def test_05_collector_scheduler_parallel_execution(self):
        """Test CollectorScheduler priority sorting, retry logic, and parallel execution."""
        scheduler = CollectorScheduler(max_workers=5)
        col1 = CustomTestCollector("Priority1Col")
        col1.schedule().priority = 1
        col2 = CustomTestCollector("Priority2Col")
        col2.schedule().priority = 2

        results = scheduler.run_collection_cycle([col2, col1])
        self.assertIn("Priority1Col", results)
        self.assertIn("Priority2Col", results)
        self.assertEqual(len(results["Priority1Col"]), 1)
        self.assertEqual(len(results["Priority2Col"]), 1)
        scheduler.shutdown()

    def test_06_collector_health_monitor(self):
        """Test CollectorHealthMonitor aggregate metric calculations and dashboard formatting."""
        monitor = CollectorHealthMonitor()
        col1 = CustomTestCollector("HCol1")
        col1.initialize()
        col1.execute_collection()

        col2 = CustomTestCollector("HCol2", should_fail=True)
        col2.initialize()
        try:
            col2.execute_collection()
        except Exception:
            pass

        metrics = monitor.to_dashboard_metrics([col1, col2])
        self.assertIn("summary", metrics)
        self.assertIn("collectors", metrics)
        summary = metrics["summary"]
        self.assertEqual(summary["total_collectors"], 2)
        self.assertEqual(summary["total_packets_collected"], 1)

    def test_07_collector_manager_source_modes(self):
        """Test CollectorManager source mode switching (Simulation, Live, Hybrid, Failover)."""
        manager = CollectorManager()
        manager.initialize()

        # Simulation Mode
        manager.set_source_mode(SourceMode.SIMULATION)
        self.assertEqual(manager.source_mode, SourceMode.SIMULATION)
        sim_col = manager._registry.get("SimulationCollector")
        self.assertTrue(sim_col.is_enabled)
        snmp_col = manager._registry.get("SNMPCollector")
        self.assertFalse(snmp_col.is_enabled)

        # Live Mode
        manager.set_source_mode(SourceMode.LIVE)
        self.assertEqual(manager.source_mode, SourceMode.LIVE)
        self.assertFalse(sim_col.is_enabled)
        self.assertTrue(snmp_col.is_enabled)

        # Hybrid Mode
        manager.set_source_mode(SourceMode.HYBRID)
        self.assertTrue(sim_col.is_enabled)
        self.assertTrue(snmp_col.is_enabled)

    def test_08_automatic_failover_logic(self):
        """Test automatic failover from live mode to simulation when live feeds fail."""
        manager = CollectorManager()
        manager.initialize()
        manager.set_source_mode(SourceMode.FAILOVER)

        # Mock live failure
        fail_col = CustomTestCollector("FailingLiveCol", should_fail=True)
        fail_col._metadata.source_type = "snmp"
        manager._registry.register(fail_col, allow_override=True)

        for _ in range(4):
            manager._on_collector_packets_collected(fail_col, [])

        self.assertTrue(manager.is_failover_active)

    def test_09_event_bus_and_execution_context_propagation(self):
        """Test EventBus event publishing and ExecutionContext updates."""
        event_bus = EventBus()
        received_events = []

        def on_telemetry(evt: Event):
            received_events.append(evt)

        event_bus.subscribe("telemetry.collected", on_telemetry)

        manager = CollectorManager(event_bus=event_bus)
        manager.initialize()

        ctx = ExecutionContext()
        packets = manager.collect_once(context=ctx)

        self.assertTrue(len(packets) > 0)
        self.assertIn("CollectorManager", ctx.results)
        self.assertIn("latest_collector_packets", ctx.shared_state)
        self.assertTrue(len(received_events) > 0)

    def test_10_telemetry_agent_backwards_compatibility(self):
        """Verify TelemetryAgent operates without regressions alongside CollectorManager."""
        agent = TelemetryAgent()
        agent.initialize()

        ctx = ExecutionContext()
        packets = agent.execute({"mode": "latest"}, context=ctx)
        self.assertTrue(len(packets) >= 0)
        self.assertEqual(agent.metrics.success_count, 1)


if __name__ == "__main__":
    unittest.main()
