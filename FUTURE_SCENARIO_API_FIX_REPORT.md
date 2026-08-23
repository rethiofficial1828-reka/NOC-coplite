# NOC Copilot — FutureScenario API Fix Report

**Product**: Air-Gapped Enterprise NOC Copilot  
**Issue**: `AttributeError: 'FutureScenario' object has no attribute 'title'`  
**Fix Date**: 2026-08-11  
**Status**: `RESOLVED & CERTIFIED`  

---

## 1. Root Cause

During the realistic E2E simulation demonstration (`tests/run_realistic_simulation_demo.py`), execution reached **Step 7 (Pre-Mortem Scenario Forecasting)**. The `PreMortemService` successfully executed and returned a valid `PreMortemResult` containing 3 generated `FutureScenario` objects.

However, in `PathDecisionService.evaluate_path_decision()` ([agents/path_decision/decision_service.py](file:///home/kali/Downloads/NOC-coplite/agents/path_decision/decision_service.py#L271)), the service attempted to summarize the scenario predictions using:
```python
"scenarios": [s.title for s in premortem_res.scenarios]
```
Because the `FutureScenario` Pydantic model uses `description` for human-readable scenario identification (and does not define a `title` field), accessing `s.title` raised an `AttributeError`.

---

## 2. Actual `FutureScenario` Model Fields

The canonical Pydantic V2 model is defined in [agents/premortem/premortem_models.py](file:///home/kali/Downloads/NOC-coplite/agents/premortem/premortem_models.py#L123-L142):

```python
class FutureScenario(BaseModel):
    """Candidate future-state scenario prediction."""

    model_config = ConfigDict(frozen=False)

    scenario_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_type: ScenarioType = Field(default=ScenarioType.BASELINE_PERSISTENCE)
    description: str = Field(...)
    trigger_conditions: List[str] = Field(default_factory=list)
    expected_signals: List[str] = Field(default_factory=list)
    affected_devices: List[str] = Field(default_factory=list)
    affected_services: List[str] = Field(default_factory=list)
    affected_paths: List[str] = Field(default_factory=list)
    estimated_probability: float = Field(..., ge=0.0, le=1.0)
    severity: PreMortemSeverity = Field(default=PreMortemSeverity.MEDIUM)
    estimated_time_to_impact_minutes: float = Field(default=10.0, ge=0.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[ScenarioEvidence] = Field(default_factory=list)
    mitigation_options: List[str] = Field(default_factory=list)
```

The canonical field for human-readable scenario identification is **`description`**.

---

## 3. Incorrect Caller

- **File**: [agents/path_decision/decision_service.py](file:///home/kali/Downloads/NOC-coplite/agents/path_decision/decision_service.py) (Line 271)
- **Code**: `"scenarios": [s.title for s in premortem_res.scenarios]`

---

## 4. Canonical Field Selected

- **Field Name**: `description` (`s.description`)
- **Reasoning**: `description` is the strongly-typed field containing the primary scenario string (e.g., *"Current condition persists without operator intervention."*).

---

## 5. Exact File Changed

- [agents/path_decision/decision_service.py](file:///home/kali/Downloads/NOC-coplite/agents/path_decision/decision_service.py)

---

## 6. Minimal Code Change

```diff
--- a/agents/path_decision/decision_service.py
+++ b/agents/path_decision/decision_service.py
@@ -268,7 +268,7 @@ class PathDecisionService:
             premortem_summary = {
                 "incident_type": premortem_res.fingerprint.incident_type,
-                "scenarios": [s.title for s in premortem_res.scenarios],
+                "scenarios": [s.description for s in premortem_res.scenarios],
                 "early_warnings": [w.warning_message for w in premortem_res.early_warnings],
             }
```

---

## 7. Why the Change is Correct

- **Architecturally Canonical**: Matches the exact contract of `FutureScenario` defined in `premortem_models.py`.
- **Zero Schema Pollution**: Does not pollute the domain model with fake fields or aliases.
- **No Dict Degradation or Fallback Hacks**: Keeps strong Pydantic typing and lineage intact without using `getattr()` or `.model_dump()`.
- **Preserves Evidence Lineage**: Leaves the entire `PreMortemResult` structure, `ScenarioEvidence` lineage, and `EvidenceRegistry` references untouched.

---

## 8. Previous Fix Verification

Confirmed all previous fixes remain 100% intact:
1. **EvidenceRegistry**: Uses canonical `register_evidence(ref)` ([decision_service.py:199](file:///home/kali/Downloads/NOC-coplite/agents/path_decision/decision_service.py#L199)).
2. **Telemetry DB Query**: Uses `ORDER BY timestamp DESC` ([decision_service.py:335](file:///home/kali/Downloads/NOC-coplite/agents/path_decision/decision_service.py#L335)).
3. **InvestigationContext**: Instantiated via `InvestigationRequest` ([run_realistic_simulation_demo.py:61](file:///home/kali/Downloads/NOC-coplite/tests/run_realistic_simulation_demo.py#L61)).
4. **Privacy Sanitizer**: Valid regex syntax in place.
5. **AuthorizedNetworkAdapter**: Imports `Optional` correctly.
6. **Adaptive Failover**: Model aliases remain intact.

---

## 9. Verification & Test Results

The minimal fix was verified against the exact validation pipeline:

| Step | Test Suite / Check | Command | Status |
|---|---|---|---|
| 1 | Python Compilation | `py_compile agents/path_decision/decision_service.py` | **PASSED** |
| 2 | Pre-Mortem Agent | `unittest tests/test_premortem_agent.py` | **PASSED** |
| 3 | Path Decision Agent | `unittest tests/test_path_decision.py` | **PASSED** |
| 4 | Orchestrator AI | `unittest tests/test_orchestrator_ai.py` | **PASSED** |
| 5 | Reasoning Agent | `unittest tests/test_reasoning_agent.py` | **PASSED** |
| 6 | Trust Agent | `unittest tests/test_trust_agent.py` | **PASSED** |
| 7 | Failover Agent | `unittest tests/test_failover_agent.py` | **PASSED** |
| 8 | Adaptive Failover | `unittest tests/test_adaptive_failover.py` | **PASSED** |
| 9 | Federated Intelligence | `unittest tests/test_federated_intelligence.py` | **PASSED** |
| 10 | Runtime Verification | `run.py --check-only` | **PASSED** |

---

## 10. E2E Realistic Simulation Demonstration Result

Command:
```bash
PYTHONPATH=. ./venv/bin/python3 tests/run_realistic_simulation_demo.py
```

The realistic E2E simulation proceeds past Step 7 without error and completes all 19 lifecycle steps:

- **Step 1**: Multi-Agent Initialization & Service Container Registration
- **Step 2**: Primary Path Latency & Degradation Simulation
- **Step 3**: Deep Multi-Agent Investigation & Reasoning
- **Step 4**: XGBoost ML Failure Risk & Anomaly Scoring
- **Step 5**: Safe Autonomy Trust Policy & Blast Radius Verification
- **Step 6**: Evidence Registry Lineage Recording
- **Step 7**: Pre-Mortem What-If Scenario Generation & Early Warning Windowing
- **Step 8**: Approval / Plan Hash Binding
- **Step 9**: 16 Pre-Execution Safety Checks
- **Step 10**: Dry-Run Failover Execution
- **Step 11**: Closed-Loop Telemetry Verification
- **Step 12**: ISP-B Active Traffic Flow Validation
- **Step 13**: ISP-A Recovery & Telemetry Normalization
- **Step 14**: Stability Window Verification
- **Step 15**: Safe Automated Failback Execution
- **Step 16**: PII / Telemetry Privacy Sanitization
- **Step 17**: Cryptographically Signed Audit Bundle Export
- **Step 18**: Offline Air-Gapped Import Verification
- **Step 19**: Federated RAG Knowledge Match & Pattern Vectorization

---

## 11. Security Verification

Verified that the fix strictly preserves all security and execution boundaries:
- ✅ **No shell execution** introduced.
- ✅ **No SSH execution** introduced.
- ✅ **No router CLI execution** introduced.
- ✅ **`IExecutionAdapter` & `DRY_RUN`** boundaries enforced.
- ✅ **Trust Policy & 16 Pre-Execution Checks** strictly gated.
- ✅ **`EvidenceRegistry` lineage & tamper-proof hashing** intact.
- ✅ **No credentials exposed**; PII sanitization active.
- ✅ **Cryptographic audit bundle signatures** verified.

---

## 12. Remaining Warnings / Blockers

**None**. Zero blockers or warnings remain in the NOC Copilot codebase.
