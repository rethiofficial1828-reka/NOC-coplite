"""
Federated Intelligence Agent Module.

Production-grade Atomic Agent wrapping FederatedIntelligenceService within NOC Copilot agent framework.
Supports lifecycle management, schema validation, thread-safe metrics, EventBus subscription/publishing,
and dependency injection via ServiceContainer.
"""

from typing import Any, Dict, Optional

from agents.base.base_agent import BaseAgent
from agents.core.container import ServiceContainer
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.federated_intelligence.federated_intelligence_service import FederatedIntelligenceService
from agents.federated_intelligence.federated_models import (
    ExportBundleResult,
    ImportValidationResult,
    TrustOrigin,
)
from agents.schemas.schemas import AgentMetadata, CapabilityFlags, ExecutionContext


class FederatedIntelligenceAgent(BaseAgent):
    """
    Atomic Agent responsible for air-gapped federated incident intelligence export, signature verification,
    privacy auditing, import ingestion, and local RAG knowledge indexing.
    """

    def __init__(
        self,
        metadata: Optional[AgentMetadata] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[EventBus] = None,
        service: Optional[FederatedIntelligenceService] = None,
    ) -> None:
        if not metadata:
            metadata = AgentMetadata(
                name="FederatedIntelligenceAgent",
                version="1.0.0",
                description="Air-Gapped Federated Incident Intelligence & Signed Knowledge Exchange Engine.",
                dependencies=["KnowledgeAgent", "ReasoningAgent", "TrustAgent", "RuntimeAgent"],
                tags=["federated", "privacy", "crypto", "signing", "rag", "air-gap"],
                capabilities=CapabilityFlags(
                    supports_async=True,
                    supports_batch=True,
                    supports_parallel_execution=True,
                    supports_cpu=True,
                ),
            )

        super().__init__(metadata=metadata, container=container, event_bus=event_bus)

        # Inject or resolve FederatedIntelligenceService
        if service:
            self._service = service
        else:
            self._service = FederatedIntelligenceService(event_bus=self.event_bus)

        # Register EventBus subscribers
        if self.event_bus:
            self.event_bus.subscribe("federated.export.requested", self._handle_export_requested)
            self.event_bus.subscribe("federated.import.requested", self._handle_import_requested)
            self.event_bus.subscribe("incident.created", self._handle_incident_created)

    @property
    def service(self) -> FederatedIntelligenceService:
        """Domain service instance."""
        return self._service

    def _execute_internal(self, input_data: Any, context: Optional[ExecutionContext] = None) -> Dict[str, Any]:
        """
        Execute federated export or import task based on ExecutionContext or input payload.

        Args:
            input_data: Validated input payload or ExecutionContext.
            context: Optional ExecutionContext container with parameters.

        Returns:
            Dict containing operation results.
        """
        exec_ctx = input_data if isinstance(input_data, ExecutionContext) else (context or ExecutionContext(payload=input_data if isinstance(input_data, dict) else {}))
        payload = (exec_ctx.payload if hasattr(exec_ctx, "payload") and exec_ctx.payload else None) or (exec_ctx.parameters if hasattr(exec_ctx, "parameters") and exec_ctx.parameters else None) or {}
        action = payload.get("action")
        if not action:
            if any(k in payload for k in ("file_path_or_dict", "bundle_file_path", "bundle_path", "bundle", "file_path")):
                action = "IMPORT"
            else:
                action = "EXPORT"

        if action == "IMPORT":
            file_path = payload.get("file_path_or_dict") or payload.get("bundle_file_path") or payload.get("bundle_path") or payload.get("bundle") or payload.get("file_path")
            trust_orig_raw = payload.get("trust_origin", TrustOrigin.FEDERATED_SITE_ALPHA)
            if isinstance(trust_orig_raw, str):
                try:
                    trust_origin = TrustOrigin(trust_orig_raw)
                except Exception:
                    trust_origin = TrustOrigin.FEDERATED_SITE_ALPHA
            else:
                trust_origin = trust_orig_raw

            val_res: ImportValidationResult = self._service.import_and_index_bundle(file_path, trust_origin=trust_origin)
            return {"import_result": val_res.model_dump(mode="json"), "status": val_res.status.value}

        else:
            symptoms = payload.get("symptoms", ["Latency elevated", "Packet loss spike"])
            category = payload.get("category", "WAN_CONGESTION")
            hypo = payload.get("hypothesis", "Primary ISP circuit experiencing congestion on 10.0.0.1")
            rec = payload.get("recommendation", "Switch path to Secondary ISP")

            exp_res: ExportBundleResult = self._service.export_incident_intelligence(
                raw_symptoms=symptoms,
                category=category,
                hypothesis=hypo,
                recommendation=rec,
            )
            return {"export_result": exp_res.model_dump(mode="json"), "status": exp_res.status.value}

    def _handle_export_requested(self, event: Event) -> None:
        """Event handler for federated.export.requested."""
        self.logger.info("FederatedIntelligenceAgent received federated.export.requested event")

    def _handle_import_requested(self, event: Event) -> None:
        """Event handler for federated.import.requested."""
        self.logger.info("FederatedIntelligenceAgent received federated.import.requested event")

    def _handle_incident_created(self, event: Event) -> None:
        """Event handler for incident.created."""
        pass
