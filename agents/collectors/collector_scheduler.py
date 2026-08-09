"""
Thread-Safe Parallel Collector Scheduler.

Manages interval polling schedules, priority ordering, parallel thread execution,
retry mechanisms with exponential backoff, and timeouts for collectors.
"""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import threading
import time
from typing import Callable, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.schemas.schemas import TelemetryPacket
from agents.collectors.collector_base import CollectorBase

logger = get_agent_logger("CollectorScheduler")


class CollectorScheduler:
    """
    Scheduler for concurrent telemetry collector polling.
    """

    def __init__(self, max_workers: int = 10) -> None:
        """
        Initialize CollectorScheduler.

        Args:
            max_workers: Maximum thread pool worker count.
        """
        self._max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="CollectorWorker")
        self._lock = threading.RLock()
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._on_packets_collected: Optional[Callable[[CollectorBase, List[TelemetryPacket]], None]] = None

    @property
    def is_running(self) -> bool:
        """Whether background scheduler loop is running."""
        with self._lock:
            return self._running

    def set_on_packets_collected_callback(
        self, callback: Optional[Callable[[CollectorBase, List[TelemetryPacket]], None]]
    ) -> None:
        """Set callback function invoked whenever packets are successfully collected."""
        with self._lock:
            self._on_packets_collected = callback

    def trigger_collector(self, collector: CollectorBase) -> List[TelemetryPacket]:
        """
        Execute a single collector with retry logic, timeout enforcement, and exponential backoff.

        Args:
            collector: Target CollectorBase instance.

        Returns:
            List of collected TelemetryPacket objects.
        """
        sched = collector.schedule()
        if not sched.enabled:
            return []

        max_retries = sched.max_retries
        backoff = sched.backoff_factor
        timeout = sched.timeout_seconds

        attempt = 0
        last_exception = None

        while attempt <= max_retries:
            attempt += 1
            future = self._executor.submit(collector.execute_collection)
            try:
                packets = future.result(timeout=timeout)
                if self._on_packets_collected:
                    try:
                        self._on_packets_collected(collector, packets)
                    except Exception as cb_err:
                        logger.error(f"Error in on_packets_collected callback: {cb_err}")
                return packets
            except FutureTimeoutError:
                err_msg = f"Collection timed out after {timeout}s (attempt {attempt}/{max_retries + 1})"
                collector.record_failure(err_msg, latency_ms=timeout * 1000.0)
                last_exception = TimeoutError(err_msg)
            except Exception as e:
                err_msg = f"Collection error: {e} (attempt {attempt}/{max_retries + 1})"
                last_exception = e

            if attempt <= max_retries:
                sleep_sec = (backoff ** (attempt - 1)) * 0.5
                logger.info(f"Retrying collector '{collector.name}' in {sleep_sec:.2f}s...")
                time.sleep(sleep_sec)

        logger.error(f"Collector '{collector.name}' failed all {max_retries + 1} attempts: {last_exception}")
        return []

    def run_collection_cycle(self, collectors: List[CollectorBase]) -> Dict[str, List[TelemetryPacket]]:
        """
        Run a single parallel collection cycle across a list of collectors.

        Collectors are sorted by priority (1 = highest priority).

        Args:
            collectors: List of active CollectorBase instances.

        Returns:
            Dict mapping collector_name -> List[TelemetryPacket].
        """
        enabled_collectors = [c for c in collectors if c.is_enabled]
        if not enabled_collectors:
            return {}

        # Sort by priority ascending (1 = highest priority)
        sorted_collectors = sorted(enabled_collectors, key=lambda c: c.schedule().priority)

        futures_map = {}
        for c in sorted_collectors:
            fut = self._executor.submit(self.trigger_collector, c)
            futures_map[c.name] = fut

        results: Dict[str, List[TelemetryPacket]] = {}
        for name, fut in futures_map.items():
            try:
                results[name] = fut.result()
            except Exception as e:
                logger.error(f"Error gathering collection result for '{name}': {e}")
                results[name] = []

        return results

    def start(self, collector_provider: Callable[[], List[CollectorBase]], interval_sec: float = 5.0) -> None:
        """
        Start the background polling loop.

        Args:
            collector_provider: Callable returning list of active collectors.
            interval_sec: Polling loop tick interval.
        """
        with self._lock:
            if self._running:
                logger.warning("CollectorScheduler is already running.")
                return

            self._running = True
            self._stop_event.clear()

            def scheduler_loop():
                logger.info("CollectorScheduler background loop started.")
                while not self._stop_event.is_set():
                    try:
                        collectors = collector_provider()
                        self.run_collection_cycle(collectors)
                    except Exception as loop_err:
                        logger.error(f"Error in CollectorScheduler loop iteration: {loop_err}", exc_info=True)

                    self._stop_event.wait(timeout=interval_sec)
                logger.info("CollectorScheduler background loop stopped.")

            self._scheduler_thread = threading.Thread(
                target=scheduler_loop, name="CollectorSchedulerThread", daemon=True
            )
            self._scheduler_thread.start()

    def stop(self) -> None:
        """Stop background scheduler loop and wait for active threads."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()

        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=3.0)

        logger.info("CollectorScheduler stopped successfully.")

    def shutdown(self) -> None:
        """Shutdown scheduler thread pool."""
        self.stop()
        self._executor.shutdown(wait=False)
