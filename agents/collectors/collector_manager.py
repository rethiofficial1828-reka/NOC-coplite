"""
Central Enterprise Collector Manager Facade.

Coordinates collector registration, source mode switching (Simulation, Live, Hybrid, Failover),
parallel background scheduling, automatic failover detection, EventBus event publishing,
and TelemetryAgent/ExecutionContext integration.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.events.event_bus import EventBus
from agents.schemas.schemas import ExecutionContext, TelemetryPacket
from agents.collectors.collector_base import CollectorBase
from agents.collectors.collector_events import (
    EVENT_TELEMETRY_COLLECTED,
    create_collector_health_event,
    create_source_mode_changed_event,
    create_telemetry_collected_event,
)
from agents.collectors.collector_health import CollectorHealthMonitor
from agents.collectors.collector_models import (
    CollectorHealth,
    CollectorState,
    SourceMode,
)
from agents.collectors.collector_registry import CollectorRegistry
from agents.collectors.collector_scheduler import CollectorScheduler

# Production collectors
from agents.collectors.simulation_collector import SimulationCollector
from agents.collectors.snmp_collector import SNMPCollector
from agents.collectors.syslog_collector import SyslogCollector
from agents.collectors.rest_collector import RESTCollector
from agents.collectors.windows_collector import WindowsCollector
from agents.collectors.linux_collector import LinuxCollector
from agents.collectors.prometheus_collector import PrometheusCollector

logger = get_agent_logger("CollectorManager")


class CollectorManager:
    """
    Central Manager and Facade for the Enterprise Telemetry Integration Layer.
    """

    _global_instance: Optional["CollectorManager"] = None
    _global_lock = threading.Lock()

    def __init__(
        self,
        registry: Optional[CollectorRegistry] = None,
        scheduler: Optional[CollectorScheduler] = None,
        event_bus: Optional[EventBus] = None,
        source_mode: SourceMode = SourceMode.SIMULATION,
    ) -> None:
        """
        Initialize CollectorManager.

        Args:
            registry: CollectorRegistry instance (defaults to global).
            scheduler: CollectorScheduler instance.
            event_bus: EventBus instance (defaults to global).
            source_mode: Initial SourceMode.
        """
        self._registry = registry or CollectorRegistry.get_global()
        self._scheduler = scheduler or CollectorScheduler(max_workers=10)
        self._event_bus = event_bus or EventBus.get_global()
        self._health_monitor = CollectorHealthMonitor(registry_provider=self._registry)
        self._source_mode = source_mode
        self._is_initialized = False
        self._lock = threading.RLock()

        # Failover tracking
        self._consecutive_live_failures = 0
        self._failover_active = False

        # Register callback with scheduler
        self._scheduler.set_on_packets_collected_callback(self._on_collector_packets_collected)

    @classmethod
    def get_global(cls) -> "CollectorManager":
        """Get or create global singleton CollectorManager instance."""
        if cls._global_instance is None:
            with cls._global_lock:
                if cls._global_instance is None:
                    cls._global_instance = cls()
        return cls._global_instance

    @property
    def source_mode(self) -> SourceMode:
        """Current ingestion source mode."""
        with self._lock:
            return self._source_mode

    @property
    def is_failover_active(self) -> bool:
        """Whether automatic failover to simulation is currently active."""
        with self._lock:
            return self._failover_active

    def set_source_mode(self, mode: SourceMode, reason: str = "User request") -> None:
        """
        Change runtime source selection mode.

        Args:
            mode: Target SourceMode (SIMULATION, LIVE, HYBRID, FAILOVER).
            reason: Description of trigger.
        """
        with self._lock:
            old_mode = self._source_mode
            if old_mode == mode:
                return

            self._source_mode = mode
            self._failover_active = False
            self._consecutive_live_failures = 0

            # Update active collector states based on new mode
            self._apply_mode_to_collectors(mode)

            # Publish event
            evt = create_source_mode_changed_event(old_mode=old_mode, new_mode=mode, reason=reason)
            self._event_bus.publish(evt)

            logger.info(f"CollectorManager source mode changed from {old_mode.value} to {mode.value} [{reason}]")

    def _apply_mode_to_collectors(self, mode: SourceMode) -> None:
        """Enable/disable registered collectors according to source mode."""
        collectors = self._registry.list_all()

        for c in collectors:
            stype = c.source_type.strip().lower()
            if mode == SourceMode.SIMULATION:
                c.set_enabled(stype == "simulation")
            elif mode == SourceMode.LIVE:
                c.set_enabled(stype != "simulation")
            elif mode == SourceMode.HYBRID:
                c.set_enabled(True)
            elif mode == SourceMode.FAILOVER:
                # Enable live collectors primarily, simulation secondary if failover active
                c.set_enabled(stype != "simulation" if not self._failover_active else stype == "simulation")

    def register_default_collectors(self) -> List[CollectorBase]:
        """
        Instantiate and register all default enterprise production collectors.

        Returns:
            List of registered CollectorBase instances.
        """
        defaults = [
            SimulationCollector(),
            SNMPCollector(),
            SyslogCollector(),
            RESTCollector(),
            WindowsCollector(),
            LinuxCollector(),
            PrometheusCollector(),
        ]

        with self._lock:
            registered = []
            for c in defaults:
                try:
                    c.initialize()
                    self._registry.register(c, allow_override=True)
                    registered.append(c)
                except Exception as e:
                    logger.error(f"Failed to initialize/register default collector '{c.name}': {e}")

            self._apply_mode_to_collectors(self._source_mode)
            logger.info(f"Registered {len(registered)} default collectors in CollectorManager.")
            return registered

    def initialize(self) -> bool:
        """
        Initialize the CollectorManager and register default collectors if empty.

        Returns:
            True if initialization succeeded.
        """
        with self._lock:
            if self._is_initialized:
                return True

            if not self._registry.list_all():
                self.register_default_collectors()

            self._is_initialized = True
            logger.info("CollectorManager initialized successfully.")
            return True

    def start_scheduler(self, interval_seconds: float = 5.0) -> None:
        """
        Start the background polling loop.

        Args:
            interval_seconds: Loop tick interval.
        """
        if not self._is_initialized:
            self.initialize()

        self._scheduler.start(
            collector_provider=self.get_active_collectors,
            interval_sec=interval_seconds,
        )
        logger.info("CollectorManager scheduler started.")

    def stop_scheduler(self) -> None:
        """Stop background scheduler."""
        self._scheduler.stop()
        logger.info("CollectorManager scheduler stopped.")

    def get_active_collectors(self) -> List[CollectorBase]:
        """
        Get list of active collectors appropriate for current source mode.

        Returns:
            List of enabled CollectorBase instances.
        """
        with self._lock:
            all_collectors = self._registry.list_all()
            return [c for c in all_collectors if c.is_enabled]

    def _on_collector_packets_collected(
        self, collector: CollectorBase, packets: List[TelemetryPacket]
    ) -> None:
        """
        Internal scheduler callback invoked when packets are collected.

        Publishes 'telemetry.collected' event onto EventBus.

        Args:
            collector: Collector instance.
            packets: List of TelemetryPacket objects.
        """
        if not packets:
            if collector.source_type != "simulation" and self._source_mode in (SourceMode.LIVE, SourceMode.FAILOVER):
                self._check_and_handle_live_failures(collector)
            return

        if collector.source_type != "simulation":
            with self._lock:
                self._consecutive_live_failures = 0

        # Publish telemetry.collected event onto EventBus
        evt = create_telemetry_collected_event(
            collector_name=collector.name,
            collector_id=collector.collector_id,
            source_type=collector.source_type,
            packets=packets,
        )
        self._event_bus.publish(evt)

        # Publish health event
        health_evt = create_collector_health_event(collector.health())
        self._event_bus.publish(health_evt)

    def _check_and_handle_live_failures(self, collector: CollectorBase) -> None:
        """Check for automatic failover trigger condition."""
        with self._lock:
            self._consecutive_live_failures += 1

            if (
                self._source_mode == SourceMode.FAILOVER
                and not self._failover_active
                and self._consecutive_live_failures >= 3
            ):
                self._failover_active = True
                logger.warning(
                    "Automatic Failover Triggered! Live collectors failed continuously. Switching to SimulationCollector."
                )

                self._apply_mode_to_collectors(SourceMode.FAILOVER)

                evt = create_source_mode_changed_event(
                    old_mode=SourceMode.FAILOVER,
                    new_mode=SourceMode.FAILOVER,
                    reason="Automatic failover to simulation triggered due to live collector failures.",
                )
                self._event_bus.publish(evt)

    def collect_once(
        self,
        collector_name: Optional[str] = None,
        context: Optional[ExecutionContext] = None,
    ) -> List[TelemetryPacket]:
        """
        Execute a synchronous single-pass collection run across active collectors.

        Args:
            collector_name: Optional specific collector name.
            context: Optional shared ExecutionContext.

        Returns:
            List of all collected TelemetryPacket instances.
        """
        if not self._is_initialized:
            self.initialize()

        target_collectors: List[CollectorBase] = []
        if collector_name:
            col = self._registry.get(collector_name)
            if col:
                target_collectors = [col]
        else:
            target_collectors = self.get_active_collectors()

        if not target_collectors:
            # Fallback to simulation collector if no live collector active
            sim = self._registry.get("SimulationCollector")
            if sim:
                target_collectors = [sim]

        all_packets: List[TelemetryPacket] = []

        for col in target_collectors:
            try:
                packets = self._scheduler.trigger_collector(col)
                all_packets.extend(packets)
            except Exception as err:
                logger.error(f"Error in collect_once for '{col.name}': {err}")

        # Update ExecutionContext if provided
        if context:
            context.results["CollectorManager"] = [p.model_dump(mode="json") for p in all_packets]
            context.shared_state["latest_collector_packets"] = {
                p.interface: p.model_dump(mode="json") for p in all_packets
            }

        return all_packets

    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get aggregated health metrics dictionary.

        Returns:
            Dict containing health summary and collector metrics.
        """
        all_cols = self._registry.list_all()
        return self._health_monitor.to_dashboard_metrics(all_cols)

    def shutdown(self) -> None:
        """Shutdown Manager and all registered collectors."""
        self.stop_scheduler()
        with self._lock:
            for col in self._registry.list_all():
                try:
                    col.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down collector '{col.name}': {e}")

            self._is_initialized = False
            logger.info("CollectorManager shut down cleanly.")
