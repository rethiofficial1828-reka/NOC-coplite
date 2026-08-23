# Adaptive Multi-Provider Failover, Failback & Network Stability Intelligence (`agents/adaptive_failover/`)

## 1. Subsystem Architecture & Operational Loop

The `agents/adaptive_failover/` subsystem evolves NOC Copilot from one-time failover execution into a continuous, stability-aware, multi-provider network path management loop:

$$\text{Detect} \rightarrow \text{Predict} \rightarrow \text{Investigate} \rightarrow \text{Reason} \rightarrow \text{Trust} \rightarrow \text{Path Decision} \rightarrow \text{Hysteresis Check} \rightarrow \text{Approve} \rightarrow \text{Execute} \rightarrow \text{Continuous Verify} \rightarrow \text{Stability Monitor} \rightarrow \text{Safe Failback}$$

```
+---------------------------------------------------------------------------------------------------+
|                              AdaptiveFailoverAgent (Atomic Agent)                                 |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                      AdaptiveFailoverService                                      |
+---------------------------------------------------------------------------------------------------+
    |             |             |            |            |           |            |            |
    v             v             v            v            v           v            v            v
Provider    Degradation    Stability    AdaptivePath  Failover   Continuous    Failback   Transition
Monitor      Detector       Engine        Scoring     Trigger     Verifier      Engine     Manager
 (Trends)   (Correlated)  (Hysteresis)   (Temporal)   Engine     (Post-Fail)   (Recovery)  (State Machine)
```

---

## 2. Component Reference

### `ProviderMonitor` (`provider_monitor.py`)
Tracks provider metric streams (latency, packet loss, jitter, utilization, errors, flaps, risk), calculates temporal health trends (`IMPROVING`, `STABLE`, `DEGRADED`, `RAPIDLY_DEGRADED`), and classifies provider state (`HEALTHY`, `WARNING`, `DEGRADED`, `CRITICAL`, `FAILED`). Preserves data origin taxonomy (`OBSERVED`, `PREDICTED`, `INFERRED`, `UNKNOWN`).

### `DegradationDetector` (`degradation_detector.py`)
Correlates multi-signal telemetry to distinguish hard network failures from gradual or predicted degradation. Generates structured `DegradationEvent` objects.

### `StabilityEngine` (`stability_engine.py`)
Enforces configurable `HysteresisPolicy` rules to prevent provider oscillation ($A \rightarrow B \rightarrow A \rightarrow B$):
- Minimum degradation duration: `30s`
- Minimum recovery duration: `60s`
- Minimum provider hold time: `300s` (5 min)
- Post-transition cooldown: `120s` (2 min)
- Maximum transitions per hour: `3`
- Active provider stickiness weight: `0.15`

### `AdaptivePathScoringEngine` (`adaptive_path_scoring.py`)
Extends Sprint 17 path scoring by integrating temporal health trends, failure probabilities, oscillation risk, and provider stickiness. Preferring a stable 79-health provider over a rapidly degrading 82-health provider.

### `FailoverTriggerEngine` (`failover_trigger.py`)
Evaluates degradation severity, hysteresis, oscillation risk, `TrustDecision`, and `PreMortemResult` to issue decision outcomes (`NO_ACTION`, `CONTINUE_MONITORING`, `REQUEST_FAILOVER`, `FAILOVER_BLOCKED`, `HUMAN_APPROVAL_REQUIRED`).

### `ContinuousVerificationEngine` (`continuous_verifier.py`)
Continuously compares BEFORE vs CURRENT vs EXPECTED metrics after failover to detect partial improvement, regression, or secondary provider degradation.

### `FailbackEngine` (`failback_engine.py`)
Evaluates primary provider recovery, requiring sustained stability windows before recommending safe failback. Employs the exact same safety pipeline: $\text{Trust} \rightarrow \text{Approval} \rightarrow \text{Precheck} \rightarrow \text{Execution} \rightarrow \text{Verification}$.

### `NetworkTransitionManager` (`transition_manager.py`)
Thread-safe state machine governing network transitions:
- `STABLE` $\rightarrow$ `DEGRADING` $\rightarrow$ `FAILOVER_CANDIDATE` $\rightarrow$ `APPROVAL_REQUIRED` $\rightarrow$ `PRECHECK` $\rightarrow$ `EXECUTING` $\rightarrow$ `VERIFYING` $\rightarrow$ `STABLE_ON_ALTERNATE`
- `STABLE_ON_ALTERNATE` $\rightarrow$ `FAILBACK_CANDIDATE` $\rightarrow$ `APPROVAL_REQUIRED` $\rightarrow$ `PRECHECK` $\rightarrow$ `FAILBACK_EXECUTION` $\rightarrow$ `VERIFYING` $\rightarrow$ `STABLE_ON_PRIMARY`

### `TransitionMemory` (`transition_memory.py`)
Preserves immutable transition history records and updates historical penalty weights based on past failover verification failures.

---

## 3. Security Boundaries & Strict Anti-Command Injection

> [!CAUTION]
> **Strict Anti-Command Injection Policy**:
> LLMs are **NEVER** permitted to generate or execute arbitrary shell commands, raw SSH strings, router CLI command scripts, firewall rule writes, or SDN controller mutations. All executions must continue through strongly-typed execution adapters (`IExecutionAdapter`). Default execution mode remains `DRY_RUN`.
