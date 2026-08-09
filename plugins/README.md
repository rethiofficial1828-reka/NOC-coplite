# NOC Copilot - Plugin Architecture Foundation

This directory houses the plugin architecture for NOC Copilot.

## Architecture Overview

The plugin layer provides extensible integration points for external network protocols, hardware vendor telemetry, custom data source ingesters, and third-party observability platforms.

Plugins operate independently of core business modules (`engine/`, `copilot/`, `faultsim/`) and register their capabilities via the `agents.core.ServiceContainer` and `agents.events.EventBus`.

## Planned Plugin Categories

### Protocol Plugins
- **SNMP Plugin**: Polling and trap handling for SNMP v2c/v3 devices.
- **Syslog Plugin**: RFC 5424 / RFC 3164 event ingestion and parser pipeline.
- **REST / Webhook Plugin**: External telemetry ingest API endpoint handlers.
- **Prometheus Plugin**: Metrics exporter and scraping adapter.

### Hardware Vendor Plugins
- **Cisco Plugin**: IOS-XE, NX-OS telemetry models and CLI parser extensions.
- **Juniper Plugin**: JunOS telemetry interfaces and alarm mappings.
- **Fortinet Plugin**: FortiGate log parsers and security event mapping.

## Developer Guidelines

1. Every plugin must define a clear initialization function or entrypoint class.
2. Plugins should expose their schemas via `agents.schemas` Pydantic models.
3. Plugins publish telemetry events directly onto `agents.events.EventBus`.
4. Plugins must register singleton or factory services inside `agents.core.ServiceContainer`.
