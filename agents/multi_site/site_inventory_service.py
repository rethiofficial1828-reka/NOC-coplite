"""
Multi-Site Inventory Service Module for NOC-Copilot v1.3.

Provides hierarchical site aggregation, device-to-site resolution, and aggregate
site health status calculation grounded in real telemetry and incident repositories.
"""

from typing import Any, Dict, List, Optional
import threading

from agents.core.logger import get_agent_logger
from agents.incident.incident_models import IncidentRecord, IncidentSeverity, IncidentStatus
from agents.incident.incident_service import IncidentService
from agents.multi_site.multi_site_models import (
    SiteHealthStatus,
    SiteRecord,
    SiteType,
)
from agents.telemetry.telemetry_service import TelemetryService
from agents.topology.topology_service import TopologyService
from config.config_manager import ConfigManager
from config.settings import DEVICE_REGISTRY, SITE_REGISTRY

logger = get_agent_logger("MultiSiteInventoryService")


class MultiSiteInventoryService:
    """
    Service responsible for multi-site inventory management, hierarchical device
    grouping, and aggregate site-level health calculation.
    """

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        telemetry_service: Optional[TelemetryService] = None,
        incident_service: Optional[IncidentService] = None,
        topology_service: Optional[TopologyService] = None,
    ) -> None:
        self._config_manager = config_manager or ConfigManager.get_instance()
        self._telemetry_service = telemetry_service or TelemetryService()
        self._incident_service = incident_service or IncidentService()
        self._topology_service = topology_service or TopologyService()
        self._lock = threading.RLock()

    def _get_raw_site_registry(self) -> List[Dict[str, Any]]:
        """Retrieve raw configured SITE_REGISTRY from config or defaults."""
        return self._config_manager.get("SITE_REGISTRY", SITE_REGISTRY)

    def _get_raw_device_registry(self) -> List[Dict[str, Any]]:
        """Retrieve raw configured DEVICE_REGISTRY from config or defaults."""
        return self._config_manager.get("DEVICE_REGISTRY", DEVICE_REGISTRY)

    def get_all_sites(self, evaluate_health: bool = True) -> List[SiteRecord]:
        """
        Retrieve all registered sites with computed real-time health and metrics.

        Args:
            evaluate_health: If True, computes live aggregate health from telemetry and incidents.

        Returns:
            List of SiteRecord objects.
        """
        with self._lock:
            raw_sites = self._get_raw_site_registry()
            site_records: List[SiteRecord] = []

            for entry in raw_sites:
                site_id = entry.get("site_id", "")
                site_name = entry.get("site_name", site_id)
                s_type_str = entry.get("site_type", "BRANCH")
                try:
                    site_type = SiteType(s_type_str)
                except ValueError:
                    site_type = SiteType.BRANCH

                record = SiteRecord(
                    site_id=site_id,
                    site_name=site_name,
                    site_type=site_type,
                    location=entry.get("location", "Regional Office"),
                    device_ids=entry.get("device_ids", []),
                    primary_providers=entry.get("primary_providers", ["ISP-A"]),
                    backup_providers=entry.get("backup_providers", ["ISP-B"]),
                    metadata=entry,
                )

                if evaluate_health:
                    self._populate_site_health(record)

                site_records.append(record)

            return site_records

    def get_site(self, site_id: str, evaluate_health: bool = True) -> Optional[SiteRecord]:
        """
        Retrieve a single site record by site_id.

        Args:
            site_id: Unique site identifier.
            evaluate_health: If True, computes live aggregate health.

        Returns:
            SiteRecord if found, else None.
        """
        with self._lock:
            for s in self.get_all_sites(evaluate_health=evaluate_health):
                if s.site_id == site_id:
                    return s
            return None

    def get_site_devices(self, site_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve full device descriptor dicts for all devices belonging to a site.

        Args:
            site_id: Unique site identifier.

        Returns:
            List of device descriptor dictionaries.
        """
        with self._lock:
            site = self.get_site(site_id, evaluate_health=False)
            if not site:
                return []

            device_registry = self._get_raw_device_registry()
            matched_devices: List[Dict[str, Any]] = []

            for dev in device_registry:
                dev_id = dev.get("id", "")
                dev_name = dev.get("name", "")
                if dev_id in site.device_ids or dev_name in site.device_ids:
                    matched_devices.append(dev)

            return matched_devices

    def get_site_for_device(self, device_id_or_name: str) -> Optional[SiteRecord]:
        """
        Resolve which site a given device ID or interface name belongs to.

        Args:
            device_id_or_name: Device ID or interface name.

        Returns:
            SiteRecord if resolved, else fallback matching site.
        """
        with self._lock:
            sites = self.get_all_sites(evaluate_health=False)
            # Direct device_id match
            for s in sites:
                if device_id_or_name in s.device_ids:
                    return s

            # Match via Device Registry device ID or name
            for dev in self._get_raw_device_registry():
                if dev.get("id") == device_id_or_name or dev.get("name") == device_id_or_name:
                    for s in sites:
                        if dev.get("id") in s.device_ids or dev.get("name") in s.device_ids:
                            return s

            return None

    def aggregate_site_health(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Compute aggregate health metrics for one or all sites.

        Args:
            site_id: Optional specific site ID. If None, aggregates all sites.

        Returns:
            Dictionary summary of site health statistics.
        """
        with self._lock:
            sites = self.get_all_sites(evaluate_health=True)
            if site_id:
                sites = [s for s in sites if s.site_id == site_id]

            total = len(sites)
            healthy = sum(1 for s in sites if s.health_status == SiteHealthStatus.HEALTHY)
            degraded = sum(1 for s in sites if s.health_status == SiteHealthStatus.DEGRADED)
            critical = sum(1 for s in sites if s.health_status == SiteHealthStatus.CRITICAL)
            offline = sum(1 for s in sites if s.health_status == SiteHealthStatus.OFFLINE)
            active_incidents = sum(s.active_incidents_count for s in sites)
            critical_incidents = sum(s.critical_incidents_count for s in sites)

            return {
                "total_sites": total,
                "healthy_sites": healthy,
                "degraded_sites": degraded,
                "critical_sites": critical,
                "offline_sites": offline,
                "total_active_incidents": active_incidents,
                "critical_active_incidents": critical_incidents,
                "sites": [s.model_dump(mode="json") for s in sites],
            }

    def _populate_site_health(self, site: SiteRecord) -> None:
        """
        Populate real-time telemetry averages and active incident metrics on a site record.
        """
        # 1. Fetch active incidents for constituent devices
        active_incidents: List[IncidentRecord] = []
        try:
            all_incidents = self._incident_service.get_all_incidents()
            for inc in all_incidents:
                if inc.status in (IncidentStatus.NEW, IncidentStatus.OPEN, IncidentStatus.ACKNOWLEDGED, IncidentStatus.IN_PROGRESS):
                    if inc.device_id in site.device_ids or inc.interface in site.device_ids:
                        active_incidents.append(inc)
                    else:
                        # Check if device belongs to this site
                        s = self.get_site_for_device(inc.device_id) or self.get_site_for_device(inc.interface)
                        if s and s.site_id == site.site_id:
                            active_incidents.append(inc)
        except Exception as e:
            logger.debug(f"Could not query incidents for site '{site.site_id}': {e}")

        site.active_incidents_count = len(active_incidents)
        site.critical_incidents_count = sum(
            1 for inc in active_incidents if inc.severity == IncidentSeverity.CRITICAL
        )

        # 2. Fetch recent telemetry across constituent devices
        latencies: List[float] = []
        losses: List[float] = []
        utils: List[float] = []
        is_any_offline = False

        for dev_key in site.device_ids:
            try:
                metrics = self._telemetry_service.repository.get_recent_metrics(dev_key, limit=1)
                if metrics:
                    m = metrics[0]
                    if hasattr(m, "latency"):
                        latencies.append(float(m.latency))
                    elif isinstance(m, dict) and "latency" in m:
                        latencies.append(float(m["latency"]))

                    if hasattr(m, "packet_loss"):
                        losses.append(float(m.packet_loss))
                    elif isinstance(m, dict) and "packet_loss" in m:
                        losses.append(float(m["packet_loss"]))

                    if hasattr(m, "utilization"):
                        utils.append(float(m.utilization))
                    elif isinstance(m, dict) and "utilization" in m:
                        utils.append(float(m["utilization"]))
            except Exception as e:
                logger.debug(f"Telemetry fetch error for dev '{dev_key}': {e}")

        avg_lat = sum(latencies) / len(latencies) if latencies else 15.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        avg_util = sum(utils) / len(utils) if utils else 25.0

        site.average_latency_ms = round(avg_lat, 2)
        site.average_loss_percent = round(avg_loss, 2)
        site.average_utilization_percent = round(avg_util, 2)

        # 3. Determine Health Status
        if is_any_offline:
            site.health_status = SiteHealthStatus.OFFLINE
        elif site.critical_incidents_count > 0 or avg_loss >= 15.0 or avg_lat >= 200.0:
            site.health_status = SiteHealthStatus.CRITICAL
        elif site.active_incidents_count > 0 or avg_loss >= 2.0 or avg_lat >= 80.0 or avg_util >= 85.0:
            site.health_status = SiteHealthStatus.DEGRADED
        else:
            site.health_status = SiteHealthStatus.HEALTHY
