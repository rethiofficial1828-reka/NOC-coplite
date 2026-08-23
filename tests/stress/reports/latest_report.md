# NOC Copilot — 100k Stress Testing Campaign Report

**Report Timestamp**: 2026-08-23T12:03:03.227482+00:00  
**Campaign Seed**: `42`  
**Status**: `✅ PASS`  
**Peak Memory (RSS)**: `110.47 MB`  

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| **Total Test Cases Executed** | **100** |
| **Passed Cases** | **100** (100.00%) |
| **Failed Cases** | **0** |
| **Safety Violations** | **0** |
| **Total Runtime** | **0.686 s** |
| **Throughput** | **145.72 cases/sec** |
| **Peak Process RSS** | **110.47 MB** |

---

## 2. Performance & Latency Metrics

- **Mean Latency**: `6.782 ms` per case
- **P95 Latency**: `33.644 ms`
- **P99 Latency**: `54.338 ms`

---

## 3. Failure Category Breakdown

| Failure Category | Count | Description |
|---|---|---|
| `SAFETY_VIOLATION` | 0 | Critical safety/security invariant breached |
| `UNEXPECTED_FAILURE` | 0 | Service exception or unhandled crash |
| `EXPECTED_FAILURE` | 0 | Precheck or validation working as intended |
| `HARNESS_FAILURE` | 0 | Test framework setup error |

---

## 4. Failure Summary by Scenario Family

```json
{}
```

---

## 5. Verification & Safety Declarations

- **Zero Unauthorized Subprocess Executions**: Confirmed.
- **DRY_RUN Isolation**: Confirmed.
- **Privacy Gate & Cryptographic Integrity**: Confirmed.
- **Bounded Memory Profile (< 1 GB RSS)**: Confirmed (`110.47 MB`).
