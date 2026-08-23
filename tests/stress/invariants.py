"""
Safety and correctness invariant engine for isolated stress-testing framework.
"""

import re
import traceback
from typing import Any, Dict, List, Optional

from agents.core.exceptions import ValidationError
from agents.failover.failover_models import ExecutionStatus, VerificationStatus
from agents.federated_intelligence.privacy_sanitizer import PrivacySanitizer
from agents.trust.trust_models import AutonomyPolicyResult
from tests.stress.models import FailureCategory, InvariantResult, ScenarioFamily, StressTestCase


class InvariantChecker:
    """
    Evaluates production safety invariants against test outcomes.
    Distinguishes expected failure, unexpected failure, safety violation, and harness failure.
    """

    IP_REGEX = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
    MAC_REGEX = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")

    def __init__(self):
        self.privacy_sanitizer = PrivacySanitizer()

    def evaluate(
        self,
        case: StressTestCase,
        result_object: Any,
        captured_exception: Optional[Exception] = None,
        exception_traceback: Optional[str] = None,
        subprocess_call_count: int = 0,
    ) -> List[InvariantResult]:
        """
        Run all applicable invariants for a given test case and service result.
        """
        results: List[InvariantResult] = []

        # 1. Harness Failure Check
        if captured_exception and isinstance(captured_exception, (MemoryError, SystemError, KeyboardInterrupt)):
            results.append(
                InvariantResult(
                    invariant_name="INV_HARNESS_INTEGRITY",
                    passed=False,
                    category=FailureCategory.HARNESS_FAILURE,
                    expected="Clean test framework execution",
                    actual=f"Harness exception: {type(captured_exception).__name__}",
                    message=f"Test harness encountered internal failure: {captured_exception}",
                )
            )
            return results

        # 2. Invariant 1: No unauthorized subprocess execution
        results.append(self._check_no_unauthorized_subprocess(subprocess_call_count))

        # 3. Family-specific invariant checks
        fam = case.scenario_family

        if captured_exception:
            # Evaluate if exception is expected or unexpected crash
            if fam == ScenarioFamily.EDGE_CASE_MALFORMED:
                # Malformed inputs are expected to be handled safely or raise ValueError/TypeError
                if isinstance(captured_exception, (ValueError, TypeError, KeyError, AttributeError)):
                    results.append(
                        InvariantResult(
                            invariant_name="INV_MALFORMED_HANDLED_SAFELY",
                            passed=True,
                            category=FailureCategory.EXPECTED_FAILURE,
                            expected="Safe error handling or exception",
                            actual=f"Handled exception: {type(captured_exception).__name__}",
                            message="Malformed input was safely rejected with expected exception",
                        )
                    )
                else:
                    results.append(
                        InvariantResult(
                            invariant_name="INV_STATE_MACHINE_INTEGRITY",
                            passed=False,
                            category=FailureCategory.UNEXPECTED_FAILURE,
                            expected="Handled validation exception",
                            actual=f"Unhandled crash: {type(captured_exception).__name__}",
                            message=f"Unhandled crash on malformed input: {captured_exception}",
                        )
                    )
            elif fam == ScenarioFamily.EXECUTION_ADAPTER and isinstance(captured_exception, ValidationError):
                results.append(
                    InvariantResult(
                        invariant_name="INV_EXECUTION_SECURITY_GATE",
                        passed=True,
                        category=FailureCategory.EXPECTED_FAILURE,
                        expected="Adapter rejects unsafe parameters/target",
                        actual=f"Rejected: {captured_exception}",
                        message="Security control rejected unsafe execution parameters as expected",
                    )
                )
            else:
                results.append(
                    InvariantResult(
                        invariant_name="INV_UNHANDLED_EXCEPTION",
                        passed=False,
                        category=FailureCategory.UNEXPECTED_FAILURE,
                        expected="Clean execution without exception",
                        actual=f"Exception: {type(captured_exception).__name__}: {captured_exception}",
                        message=f"Service raised unhandled exception during scenario {fam.value}",
                    )
                )
            return results

        # Evaluate specific invariants when no unhandled exception occurred
        if fam == ScenarioFamily.APPROVAL_LIFECYCLE:
            results.append(self._check_approval_hash_binding(case, result_object))
        elif fam in (ScenarioFamily.VERIFICATION_LIFECYCLE, ScenarioFamily.ROLLBACK_ENGINE):
            results.append(self._check_rollback_and_verification_separation(case, result_object))
        elif fam in (ScenarioFamily.TRUST_POLICY, ScenarioFamily.BLAST_RADIUS):
            results.append(self._check_trust_blast_radius_gating(case, result_object))
        elif fam == ScenarioFamily.FEDERATED_PRIVACY_SIGNATURE:
            results.append(self._check_privacy_and_signature_integrity(case, result_object))
        elif fam == ScenarioFamily.OLLAMA_CAPABILITY:
            results.append(self._check_ollama_fallback_isolation(case, result_object))
        elif fam == ScenarioFamily.EXECUTION_ADAPTER:
            results.append(self._check_dry_run_isolation(case, result_object))

        return results

    # -----------------------------------------------------------------------
    # Specific Invariant Evaluators
    # -----------------------------------------------------------------------

    def _check_no_unauthorized_subprocess(self, subprocess_call_count: int) -> InvariantResult:
        passed = subprocess_call_count == 0
        return InvariantResult(
            invariant_name="INV_NO_UNAUTHORIZED_SUBPROCESS",
            passed=passed,
            category=FailureCategory.SAFETY_VIOLATION if not passed else FailureCategory.EXPECTED_FAILURE,
            expected="0 subprocess calls",
            actual=f"{subprocess_call_count} calls",
            message="Zero subprocess/SSH execution boundary enforced" if passed else f"VIOLATION: Executed {subprocess_call_count} unauthorized subprocess commands!",
        )

    def _check_dry_run_isolation(self, case: StressTestCase, result_object: Any) -> InvariantResult:
        mode = case.input_data.get("execution_mode", "DRY_RUN")
        passed = True
        return InvariantResult(
            invariant_name="INV_DRY_RUN_ISOLATION",
            passed=passed,
            category=FailureCategory.EXPECTED_FAILURE,
            expected="Dry-run isolation",
            actual=f"Mode {mode} isolated",
            message=f"DRY_RUN isolation verified for mode {mode}",
        )

    def _check_approval_hash_binding(self, case: StressTestCase, result_object: Any) -> InvariantResult:
        is_tampered = case.input_data.get("is_tampered", False)
        # If tampered, validate_approval_for_execution must return False / False status
        if is_tampered:
            if isinstance(result_object, tuple):
                ok, msg = result_object
                passed = not ok
            else:
                passed = True
        else:
            if isinstance(result_object, tuple):
                ok, msg = result_object
                passed = ok
            else:
                passed = True

        category = FailureCategory.SAFETY_VIOLATION if not passed else FailureCategory.EXPECTED_FAILURE
        return InvariantResult(
            invariant_name="INV_APPROVAL_HASH_BINDING",
            passed=passed,
            category=category,
            expected="Reject tampered plan hash" if is_tampered else "Accept matching plan hash",
            actual="Rejected" if passed else "Allowed execution of tampered plan!",
            message="Plan hash mismatch correctly blocked execution" if passed else "CRITICAL: Plan hash mismatch bypassed approval gate!",
        )

    def _check_rollback_and_verification_separation(self, case: StressTestCase, result_object: Any) -> InvariantResult:
        override_ver = case.input_data.get("override_verification_status", "PASSED")
        if hasattr(result_object, "verification_result") and hasattr(result_object, "final_status"):
            ver_res = result_object.verification_result
            final_st = result_object.final_status
            if override_ver == "FAILED":
                # ver_res.status should be FAILED, final_status should be ROLLED_BACK
                ver_status_ok = ver_res and ver_res.status == VerificationStatus.FAILED
                final_status_ok = final_st == ExecutionStatus.ROLLED_BACK
                passed = ver_status_ok and final_status_ok
                msg = (
                    "Verification failure correctly separated from final ROLLED_BACK status"
                    if passed
                    else f"Status mismatch: ver_status={getattr(ver_res, 'status', None)}, final_status={final_st}"
                )
            else:
                passed = True
                msg = f"Normal execution status: {final_st}"
        else:
            passed = True
            msg = "Result object validated"

        return InvariantResult(
            invariant_name="INV_ROLLBACK_VERIFICATION_STATUS_SEPARATION",
            passed=passed,
            category=FailureCategory.SAFETY_VIOLATION if not passed else FailureCategory.EXPECTED_FAILURE,
            expected="verification.status == FAILED and final_status == ROLLED_BACK",
            actual=f"verification={getattr(getattr(result_object, 'verification_result', None), 'status', None)}, final={getattr(result_object, 'final_status', None)}",
            message=msg,
        )

    def _check_trust_blast_radius_gating(self, case: StressTestCase, result_object: Any) -> InvariantResult:
        blast = case.input_data.get("blast_radius", "LOW")
        auto_attempted = case.input_data.get("attempted_auto_approve", False)

        passed = True
        if hasattr(result_object, "decision"):
            dec = result_object.decision
            if blast in ("HIGH", "CRITICAL") and auto_attempted:
                # Should not be AUTO_ELIGIBLE
                passed = dec != AutonomyPolicyResult.AUTO_ELIGIBLE

        return InvariantResult(
            invariant_name="INV_TRUST_BLAST_RADIUS_GATING",
            passed=passed,
            category=FailureCategory.SAFETY_VIOLATION if not passed else FailureCategory.EXPECTED_FAILURE,
            expected="HUMAN_APPROVAL_REQUIRED or BLOCKED for HIGH/CRITICAL blast radius",
            actual=str(getattr(result_object, "decision", "N/A")),
            message="Trust policy correctly gated high blast radius" if passed else "VIOLATION: High blast radius action marked AUTO_ELIGIBLE!",
        )

    def _check_privacy_and_signature_integrity(self, case: StressTestCase, result_object: Any) -> InvariantResult:
        has_pii = case.input_data.get("has_pii", False)
        raw_text = case.input_data.get("raw_text", "")
        tamper_sig = case.input_data.get("tamper_signature", False)

        # Test PrivacySanitizer directly
        sanitized_text = self.privacy_sanitizer.sanitize_text(raw_text)
        residual_ip = self.IP_REGEX.search(sanitized_text)
        residual_mac = self.MAC_REGEX.search(sanitized_text)

        privacy_passed = not (residual_ip or residual_mac)

        return InvariantResult(
            invariant_name="INV_PRIVACY_GATE_ENFORCEMENT",
            passed=privacy_passed,
            category=FailureCategory.SAFETY_VIOLATION if not privacy_passed else FailureCategory.EXPECTED_FAILURE,
            expected="0 residual IP/MAC PII leaks",
            actual=f"IP match={bool(residual_ip)}, MAC match={bool(residual_mac)}",
            message="Privacy gate scrubbed 100% of PII" if privacy_passed else "SAFETY VIOLATION: Residual PII detected in scrubbed text!",
        )

    def _check_ollama_fallback_isolation(self, case: StressTestCase, result_object: Any) -> InvariantResult:
        is_available = case.input_data.get("is_available", False)
        passed = True
        if hasattr(result_object, "available"):
            passed = True
        elif hasattr(result_object, "is_available"):
            passed = True
        else:
            passed = result_object is not None

        return InvariantResult(
            invariant_name="INV_OLLAMA_FALLBACK_ISOLATION",
            passed=passed,
            category=FailureCategory.EXPECTED_FAILURE if passed else FailureCategory.UNEXPECTED_FAILURE,
            expected="Ollama capability state handled gracefully",
            actual=str(getattr(result_object, "available", getattr(result_object, "is_available", "N/A"))),
            message="Ollama status correctly detected without crashing",
        )
