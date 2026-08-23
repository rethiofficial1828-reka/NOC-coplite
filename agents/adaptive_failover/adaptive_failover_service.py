"""
Adaptive Failover Service Module for Adaptive Multi-Provider Failover Subsystem.

Primary domain orchestration service coordinating ProviderMonitor, DegradationDetector, StabilityEngine,
AdaptivePathScoringEngine, FailoverTriggerEngine, FailbackEngine, ContinuousVerificationEngine,
NetworkTransitionManager, and FailoverService into an integrated, closed-loop network stability engine.
"""

from datetime import datetime, timezone
import threading
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.events.event import Event
from agents.events.event_bus import EventBus
from agents.adaptive_failover.adaptive_models import (
    AdaptiveFailoverResult,
    AdaptiveFailoverStatistics,
    FailbackStatus,
    HysteresisPolicy,
    ProviderComparison,
    ProviderHealthSnapshot,
    TransitionRecord,
    TransitionStatus,
)
from agents.adaptive_failover.adaptive_path_scoring import AdaptivePathScoringEngine
from agents.adaptive_failover.continuous_verifier import ContinuousVerificationEngine
from agents.adaptive_failover.degradation_detector import DegradationDetector
from agents.adaptive_failover.failback_engine import FailbackEngine
from agents.adaptive_failover.failover_trigger import FailoverTriggerEngine
from agents.adaptive_failover.provider_monitor import ProviderMonitor
from agents.adaptive_failover.stability_engine import StabilityEngine
from agents.adaptive_failover.transition_manager import NetworkTransitionManager
from agents.adaptive_failover.transition_memory import TransitionMemory
from agents.failover.failover_models import ExecutionMode, ExecutionStatus, VerificationStatus
from agents.failover.failover_service import FailoverService
from agents.orchestrator_ai.investigation_context import InvestigationContext

logger = get_agent_logger("AdaptiveFailoverService")


class AdaptiveFailoverService:
    """
    Domain Orchestration Service for Sprint 19 Adaptive Multi-Provider Failover & Stability Subsystem.
    """

    def __init__(
        self,
        provider_monitor: Optional[ProviderMonitor] = None,
        degradation_detector: Optional[DegradationDetector] = None,
        stability_engine: Optional[StabilityEngine] = None,
        adaptive_scoring: Optional[AdaptivePathScoringEngine] = None,
        trigger_engine: Optional[FailoverTriggerEngine] = None,
        continuous_verifier: Optional[ContinuousVerificationEngine] = None,
        failback_engine: Optional[FailbackEngine] = None,
        transition_manager: Optional[NetworkTransitionManager] = None,
        transition_memory: Optional[TransitionMemory] = None,
        failover_service: Optional[FailoverService] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.policy = HysteresisPolicy()
        self.provider_monitor = provider_monitor or ProviderMonitor()
        self.degradation_detector = degradation_detector or DegradationDetector()
        self.stability_engine = stability_engine or StabilityEngine(policy=self.policy)
        self.adaptive_scoring = adaptive_scoring or AdaptivePathScoringEngine()
        self.trigger_engine = trigger_engine or FailoverTriggerEngine()
        self.continuous_verifier = continuous_verifier or ContinuousVerificationEngine()
        self.failback_engine = failback_engine or FailbackEngine(hysteresis_policy=self.policy, stability_engine=self.stability_engine)
        self.transition_manager = transition_manager or NetworkTransitionManager()
        self.transition_memory = transition_memory or TransitionMemory()
        self.failover_service = failover_service or FailoverService(event_bus=event_bus)
        self.event_bus = event_bus

        self._stats = AdaptiveFailoverStatistics()
        self._lock = threading.RLock()

    def process_adaptive_failover_cycle(
        self,
        active_provider: str = "ISP-A",
        candidate_provider: str = "ISP-B",
        active_metrics_override: Optional[Dict[str, Any]] = None,
        candidate_metrics_override: Optional[Dict[str, Any]] = None,
        degradation_duration_sec: float = 0.0,
        recovery_duration_sec: float = 0.0,
        context: Optional[InvestigationContext] = None,
    ) -> AdaptiveFailoverResult:
        """
        Execute full adaptive multi-provider monitoring and decision cycle.
        """
        with self._lock:
            req_id = str(uuid.uuid4())
            self._stats.total_evaluations += 1

            # 1. Evaluate Snapshots
            active_snap = self.provider_monitor.evaluate_provider(active_provider, "Branch3-Uplink", active_metrics_override)
            cand_snap = self.provider_monitor.evaluate_provider(candidate_provider, "Branch3-Backup", candidate_metrics_override)

            # Apply historical penalties from TransitionMemory
            active_snap.health_score = max(0.0, active_snap.health_score - self.transition_memory.get_historical_penalty(active_provider))
            cand_snap.health_score = max(0.0, cand_snap.health_score - self.transition_memory.get_historical_penalty(candidate_provider))

            # 2. Score & Compare Providers
            ranked_snaps = self.adaptive_scoring.score_adaptive_providers([active_snap, cand_snap], active_provider_name=active_provider)
            top_rec = ranked_snaps[0].provider_name

            comparison = ProviderComparison(
                active_provider=active_snap,
                alternative_providers=[cand_snap],
                recommended_provider=top_rec,
                score_delta=round(abs(ranked_snaps[0].health_score - ranked_snaps[1].health_score), 1),
                trend_justification=f"Top candidate '{top_rec}' (Health={ranked_snaps[0].health_score:.1f}, Trend={ranked_snaps[0].health_trend})",
            )

            # 3. Detect Degradation
            deg_event = self.degradation_detector.detect_degradation(active_snap, duration_sec=degradation_duration_sec)
            if deg_event and self.event_bus:
                self._publish_event("provider.degradation.detected", {"request_id": req_id, "provider": active_provider, "signals": deg_event.correlated_signals})

            # 4. Evaluate Hysteresis Policy & Oscillation Risk
            h_passed, h_reason = self.stability_engine.validate_hysteresis_preconditions(
                active_provider=active_provider,
                target_provider=candidate_provider,
                degradation_duration_sec=degradation_duration_sec,
                is_hard_failure=deg_event.is_hard_failure if deg_event else False,
            )

            osc_assessment = self.stability_engine.evaluate_oscillation_risk(active_provider)
            if not h_passed:
                self._stats.oscillations_blocked += 1
                if self.event_bus:
                    self._publish_event("oscillation.detected", {"request_id": req_id, "provider": active_provider, "reason": h_reason})

            # 5. Evaluate Failover Trigger
            trigger = self.trigger_engine.evaluate_trigger(
                active_snapshot=active_snap,
                candidate_snapshot=cand_snap,
                degradation_event=deg_event,
                oscillation_assessment=osc_assessment,
                hysteresis_passed=h_passed,
                hysteresis_reason=h_reason,
            )

            # 6. Check Failback Candidate Status
            failback_cand = self.failback_engine.evaluate_failback(
                primary_snapshot=active_snap if active_provider == "ISP-A" else cand_snap,
                current_active_snapshot=cand_snap if active_provider == "ISP-A" else active_snap,
                recovery_duration_sec=recovery_duration_sec,
            )

            # 7. Execute State Machine Transition if Failover Triggered
            cont_verif = None
            if trigger.action == "REQUEST_FAILOVER" and h_passed:
                self.transition_manager.transition_to(TransitionStatus.DEGRADING)
                self.transition_manager.transition_to(TransitionStatus.FAILOVER_CANDIDATE)
                self.transition_manager.transition_to(TransitionStatus.APPROVAL_REQUIRED)
                self.transition_manager.transition_to(TransitionStatus.PRECHECK)

                override_tel = None
                override_r = None
                if active_metrics_override:
                    override_tel = {
                        "latency": active_metrics_override.get("latency_ms", 195.0),
                        "packet_loss": active_metrics_override.get("packet_loss_percent", 8.5),
                        "utilization": active_metrics_override.get("utilization", 96.0),
                    }
                    override_r = active_metrics_override.get("failure_risk", 0.91)

                # Execute Failover Pipeline via FailoverService
                failover_run = self.failover_service.execute_failover_pipeline(
                    target_interface_or_device="Branch3-Uplink",
                    execution_mode=ExecutionMode.DRY_RUN,
                    auto_approve=True,
                    context=context,
                    override_telemetry=override_tel,
                    override_risk=override_r,
                )

                if failover_run.final_status in (ExecutionStatus.COMPLETED, ExecutionStatus.EXECUTED, VerificationStatus.PASSED) or (failover_run.execution_result and failover_run.execution_result.status in (ExecutionStatus.EXECUTED, ExecutionStatus.COMPLETED)):
                    self.transition_manager.transition_to(TransitionStatus.EXECUTING)
                    self.transition_manager.transition_to(TransitionStatus.VERIFYING)
                    self.transition_manager.transition_to(TransitionStatus.STABLE_ON_ALTERNATE, provider_change=True, new_active_provider=top_rec)
                    self._stats.total_failovers += 1

                    # Record in StabilityEngine and TransitionMemory
                    tr_rec = TransitionRecord(
                        request_id=req_id,
                        from_provider=active_provider,
                        to_provider=top_rec,
                        reason=trigger.reason,
                        status=TransitionStatus.STABLE_ON_ALTERNATE,
                    )
                    self.stability_engine.record_transition(tr_rec)
                    self.transition_memory.record_transition_event(tr_rec, verification_passed=True)

                    # Continuous Post-Transition Verification
                    cont_verif = self.continuous_verifier.evaluate_continuous_verification(
                        before_snapshot=active_snap,
                        current_snapshot=cand_snap,
                    )

            res = AdaptiveFailoverResult(
                request_id=req_id,
                active_provider=self.transition_manager.active_provider,
                recommended_provider=top_rec,
                transition_status=self.transition_manager.current_state,
                failback_status=failback_cand.status,
                provider_comparison=comparison,
                trigger=trigger,
                continuous_verification=cont_verif,
                failback_candidate=failback_cand,
                hysteresis_policy=self.policy,
                audit_reference=f"ADAPTIVE-{uuid.uuid4().hex[:8].upper()}",
                timestamp=datetime.now(timezone.utc),
            )

            logger.info(
                f"AdaptiveFailoverService cycle completed: Active Provider = '{res.active_provider}', "
                f"Status = '{res.transition_status.value}', Failback Status = '{res.failback_status.value}'"
            )

            return res

    def get_statistics(self) -> AdaptiveFailoverStatistics:
        """Return aggregate statistics."""
        with self._lock:
            self._stats.active_provider = self.transition_manager.active_provider
            self._stats.current_state = self.transition_manager.current_state
            return self._stats

    def _publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Helper to publish EventBus events."""
        if self.event_bus:
            try:
                evt = Event(event_type=event_type, source="AdaptiveFailoverService", payload=payload)
                self.event_bus.publish(evt)
            except Exception as e:
                logger.warning(f"EventBus publish error for '{event_type}': {e}")
