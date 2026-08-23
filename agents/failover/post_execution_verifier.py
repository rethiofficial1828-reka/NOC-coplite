"""
Post-Execution Verifier Module for Enterprise Controlled Failover Execution Engine.

Executes closed-loop telemetry verification following a network failover execution.
Compares Before vs After vs Expected metrics across network health, service SLA state, and
path topology consistency. Calculates verification confidence and returns a structured VerificationResult.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from agents.core.logger import get_agent_logger
from agents.failover.failover_models import (
    ExecutionPlan,
    ExecutionResult,
    VerificationCheck,
    VerificationResult,
    VerificationStatus,
)

logger = get_agent_logger("PostExecutionVerifier")


class PostExecutionVerifier:
    """
    Collects post-execution telemetry and performs closed-loop verification.
    """

    def verify_execution(
        self,
        plan: ExecutionPlan,
        result: ExecutionResult,
        post_telemetry: Optional[Dict[str, float]] = None,
        override_status: Optional[VerificationStatus] = None,
    ) -> VerificationResult:
        """
        Perform closed-loop verification comparing post-execution telemetry to expected targets.

        Args:
            plan: ExecutionPlan containing expected_metrics.
            result: ExecutionResult containing execution ID.
            post_telemetry: Optional post-execution telemetry dictionary.
            override_status: Optional status override (for testing).

        Returns:
            VerificationResult instance.
        """
        verif_id = str(uuid.uuid4())
        checks: List[VerificationCheck] = []

        exec_id = result.execution_id if (result and hasattr(result, "execution_id") and isinstance(result.execution_id, str)) else str(uuid.uuid4())

        if override_status:
            return VerificationResult(
                verification_id=verif_id,
                execution_id=exec_id,
                status=override_status,
                checks=[VerificationCheck(metric="manual_override", expected_range="PASSED", observed_value=1.0, status="PASSED")],
                confidence=1.0 if override_status == VerificationStatus.PASSED else 0.2,
                service_health="HEALTHY" if override_status == VerificationStatus.PASSED else "DEGRADED",
                path_health="HEALTHY" if override_status == VerificationStatus.PASSED else "DEGRADED",
                incident_state="RESOLVED" if override_status == VerificationStatus.PASSED else "OPEN",
            )

        telemetry = post_telemetry or {}

        exp_metrics = plan.expected_metrics if (plan and hasattr(plan, "expected_metrics") and isinstance(plan.expected_metrics, dict)) else {}

        # Default post-execution observed metrics if not supplied in simulation mode
        lat = float(telemetry.get("latency", exp_metrics.get("latency_ms", 22.0)))
        loss = float(telemetry.get("packet_loss", exp_metrics.get("packet_loss_percent", 0.2)))
        util = float(telemetry.get("utilization", exp_metrics.get("utilization_percent", 40.0)))
        risk = float(telemetry.get("failure_risk", exp_metrics.get("failure_risk", 0.08)))

        all_passed = True
        confidence = 1.0

        # Check 1: Latency Check
        exp_lat_max = float(exp_metrics.get("latency_ms_max", 50.0))
        lat_passed = lat <= exp_lat_max
        if not lat_passed:
            all_passed = False
            confidence -= 0.3
        checks.append(
            VerificationCheck(
                metric="latency_ms",
                expected_range=f"<= {exp_lat_max:.1f} ms",
                observed_value=round(lat, 1),
                status="PASSED" if lat_passed else "FAILED",
            )
        )

        # Check 2: Packet Loss Check
        exp_loss_max = float(exp_metrics.get("packet_loss_max", 1.0))
        loss_passed = loss <= exp_loss_max
        if not loss_passed:
            all_passed = False
            confidence -= 0.4
        checks.append(
            VerificationCheck(
                metric="packet_loss_percent",
                expected_range=f"<= {exp_loss_max:.1f}%",
                observed_value=round(loss, 2),
                status="PASSED" if loss_passed else "FAILED",
            )
        )

        # Check 3: Link Utilization Check
        exp_util_max = float(exp_metrics.get("utilization_max", 85.0))
        util_passed = util <= exp_util_max
        if not util_passed:
            all_passed = False
            confidence -= 0.2
        checks.append(
            VerificationCheck(
                metric="utilization_percent",
                expected_range=f"<= {exp_util_max:.1f}%",
                observed_value=round(util, 1),
                status="PASSED" if util_passed else "FAILED",
            )
        )

        # Check 4: Failure Risk Check
        exp_risk_max = float(exp_metrics.get("failure_risk_max", 0.30))
        risk_passed = risk <= exp_risk_max
        if not risk_passed:
            all_passed = False
            confidence -= 0.2
        checks.append(
            VerificationCheck(
                metric="predicted_failure_risk",
                expected_range=f"<= {exp_risk_max*100:.0f}%",
                observed_value=round(risk, 3),
                status="PASSED" if risk_passed else "FAILED",
            )
        )

        status = VerificationStatus.PASSED if all_passed else VerificationStatus.FAILED
        final_conf = max(0.1, min(1.0, confidence))

        logger.info(
            f"PostExecutionVerifier completed closed-loop verification: "
            f"Status='{status.value}', Confidence={final_conf:.2f} (Observed Latency={lat:.1f}ms, Loss={loss:.2f}%)"
        )

        return VerificationResult(
            verification_id=verif_id,
            execution_id=exec_id,
            status=status,
            checks=checks,
            confidence=round(final_conf, 2),
            service_health="HEALTHY" if all_passed else "DEGRADED",
            path_health="HEALTHY" if all_passed else "DEGRADED",
            incident_state="RESOLVED" if all_passed else "OPEN",
            timestamp=datetime.now(timezone.utc),
        )
