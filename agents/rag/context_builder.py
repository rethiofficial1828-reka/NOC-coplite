"""
Context Builder (CAG) Module.

Implements ContextBuilder for Context-Augmented Generation (CAG).
Aggregates live operational state from TelemetryAgent, PredictionAgent, IncidentAgent,
RecommendationAgent, TopologyAgent, and ExecutionContext into a unified CAGContext model.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.core.logger import get_agent_logger
from agents.rag.interfaces import IContextBuilder
from agents.rag.models import CAGContext, ContextMetrics

logger = get_agent_logger("ContextBuilder")


class ContextBuilder(IContextBuilder):
    """
    Production Context-Augmented Generation (CAG) Context Builder.

    Collects, normalises, and aggregates multi-agent state into a single CAGContext model.
    """

    def build_context(
        self,
        query: str = "",
        device_id: str = "",
        execution_context: Optional[Any] = None,
    ) -> CAGContext:
        """
        Build unified CAGContext model from shared state and execution context.

        Args:
            query: Operator request text.
            device_id: Primary device under analysis.
            execution_context: Shared ExecutionContext from orchestrator.

        Returns:
            CAGContext model instance.
        """
        shared_state: Dict[str, Any] = {}
        results_state: Dict[str, Any] = {}

        if execution_context is not None:
            if hasattr(execution_context, "shared_state"):
                shared_state = getattr(execution_context, "shared_state") or {}
            if hasattr(execution_context, "results"):
                results_state = getattr(execution_context, "results") or {}

        # 1. Telemetry State
        telemetry_data = self._extract_state(shared_state, results_state, "latest_telemetry", "TelemetryAgent")

        # 2. Prediction State
        prediction_data = self._extract_state(shared_state, results_state, "latest_prediction", "PredictionAgent")

        # 3. Incident State
        incident_data = self._extract_state(shared_state, results_state, "latest_incident", "IncidentAgent")

        # 4. Recommendation State
        recommendation_data = self._extract_state(shared_state, results_state, "latest_recommendation", "RecommendationAgent")

        # 5. Topology State
        topology_data = self._extract_state(shared_state, results_state, "latest_topology", "TopologyAgent")

        # Extract resolved device_id if omitted
        resolved_device = device_id
        if not resolved_device:
            resolved_device = (
                incident_data.get("device_id")
                or telemetry_data.get("device_id")
                or topology_data.get("device_id")
                or "unknown"
            )

        interface = (
            telemetry_data.get("interface")
            or prediction_data.get("interface")
            or topology_data.get("interface")
            or ""
        )

        # Compute Metrics
        metrics = ContextMetrics(
            total_characters=len(query) + len(str(telemetry_data)) + len(str(topology_data)),
            total_tokens_estimated=max(1, (len(query) + len(str(topology_data))) // 4),
            telemetry_present=bool(telemetry_data),
            prediction_present=bool(prediction_data),
            incident_present=bool(incident_data),
            recommendation_present=bool(recommendation_data),
            topology_present=bool(topology_data),
            retrieved_chunks_count=0,
        )

        context_obj = CAGContext(
            operator_query=query,
            device_id=resolved_device,
            interface=interface,
            telemetry_data=telemetry_data,
            prediction_data=prediction_data,
            incident_data=incident_data,
            recommendation_data=recommendation_data,
            topology_data=topology_data,
            created_at=datetime.now(timezone.utc),
            metrics=metrics,
        )

        logger.info(
            f"ContextBuilder built CAGContext for device '{resolved_device}' "
            f"(telemetry={metrics.telemetry_present}, incident={metrics.incident_present}, topology={metrics.topology_present})."
        )
        return context_obj

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_state(
        shared_state: Dict[str, Any],
        results_state: Dict[str, Any],
        shared_key: str,
        agent_name: str,
    ) -> Dict[str, Any]:
        """Extract latest dict state payload from shared_state or results dictionary."""
        val = shared_state.get(shared_key)
        if isinstance(val, dict):
            # If sub-dict keyed by result_id, pick first entry
            if val and not any(k in ("device_id", "incident_id", "packet_id") for k in val.keys()):
                first_val = next(iter(val.values()), {})
                if isinstance(first_val, dict):
                    return first_val
            return val

        res = results_state.get(agent_name)
        if isinstance(res, list) and res:
            first_item = res[0]
            if isinstance(first_item, dict):
                return first_item
        elif isinstance(res, dict):
            return res

        return {}
