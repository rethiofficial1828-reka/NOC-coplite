"""
Atomic Runtime Agent for Enterprise Hardware & Runtime Capability Discovery.

Inherits BaseAgent to inspect host platform hardware, virtualization context, GPU capabilities,
Ollama endpoints, and LLM model availability.

CRITICAL SAFETY BOUNDARY:
RuntimeAgent performs read-only detection and event publishing only.
It NEVER executes network configuration changes, router CLI, SSH commands, firewall updates,
SDN modifications, or incident diagnosis.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.core.exceptions import ValidationError
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.runtime.runtime_models import (
    CapabilityStatus,
    RuntimeCapabilities,
    RuntimeHealth,
)
from agents.runtime.runtime_service import RuntimeService
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class RuntimeAgent(BaseAgent):
    """
    Atomic Agent responsible for discovering, monitoring, and reporting runtime capabilities.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        runtime_service: Optional[RuntimeService] = None,
    ) -> None:
        default_meta = AgentMetadata(
            name="RuntimeAgent",
            version="1.0.0",
            description="Atomic agent inspecting host platform hardware, GPU acceleration, and Ollama capabilities.",
            capabilities=CapabilityFlags(supports_cpu=True, supports_parallel_execution=True),
        )
        super().__init__(metadata=metadata or default_meta, container=container, event_bus=event_bus)
        self._runtime_service = runtime_service or RuntimeService()

    def validate_input(self, input_data: Any) -> Dict[str, Any]:
        """Validate input parameters."""
        if input_data is None or isinstance(input_data, (dict, str)):
            return {"force_refresh": True if isinstance(input_data, str) and input_data.lower() == "refresh" else False}
        elif isinstance(input_data, dict):
            return input_data
        else:
            raise ValidationError(f"RuntimeAgent expects dict or str, got {type(input_data)}")

    def validate_output(self, output_data: Any) -> RuntimeCapabilities:
        """Validate output is RuntimeCapabilities schema."""
        if isinstance(output_data, RuntimeCapabilities):
            return output_data
        raise ValidationError(f"RuntimeAgent output must be RuntimeCapabilities, got {type(output_data)}")

    def _execute_internal(
        self,
        validated_input: Dict[str, Any],
        context: Optional[ExecutionContext] = None,
    ) -> RuntimeCapabilities:
        """
        Execute runtime capability discovery and publish lifecycle events.
        """
        force_refresh = validated_input.get("force_refresh", False)
        caps = self._runtime_service.get_capabilities(force_refresh=force_refresh)

        # Publish lifecycle events over EventBus if present
        if self._event_bus:
            payload = caps.model_dump(mode="json")
            self._event_bus.publish(Event(event_type="runtime.detected", source=self.name, payload=payload))

            if caps.gpu_status == CapabilityStatus.AVAILABLE:
                self._event_bus.publish(Event(event_type="runtime.gpu.detected", source=self.name, payload=payload))

            if caps.ollama_available:
                self._event_bus.publish(Event(event_type="runtime.ollama.detected", source=self.name, payload=payload))

            if caps.qwen_available:
                self._event_bus.publish(Event(event_type="runtime.model.detected", source=self.name, payload=payload))

            self._event_bus.publish(
                Event(event_type="runtime.inference.selected", source=self.name, payload={"backend": caps.selected_backend.value})
            )

            if caps.runtime_health != RuntimeHealth.READY:
                self._event_bus.publish(
                    Event(
                        event_type="runtime.degraded",
                        source=self.name,
                        payload={"health": caps.runtime_health.value, "reason": caps.degradation_reason},
                    )
                )
                self._event_bus.publish(
                    Event(
                        event_type="runtime.health.changed",
                        source=self.name,
                        payload={"health": caps.runtime_health.value, "reason": caps.degradation_reason},
                    )
                )

        return caps
