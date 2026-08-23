# Controlled Failover Execution & Closed-Loop Verification Engine (`agents/failover/`)

## 1. Subsystem Architecture

The `agents/failover/` subsystem evolves NOC Copilot from an advisory decision system into an enterprise closed-loop execution and verification platform:

$$\text{Predict} \rightarrow \text{Investigate} \rightarrow \text{Reason} \rightarrow \text{Trust} \rightarrow \text{Recommend} \rightarrow \text{Approve} \rightarrow \text{Precheck} \rightarrow \text{Execute} \rightarrow \text{Verify} \rightarrow \text{Confirm / Rollback}$$

```
+---------------------------------------------------------------------------------------------------+
|                                      FailoverAgent (Atomic Agent)                                 |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                           FailoverService                                         |
+---------------------------------------------------------------------------------------------------+
    |                   |                  |                     |                   |
    v                   v                  v                     v                   v
ApprovalManager   PreExecutionValidator  IExecutionAdapter   PostExecutionVerifier   RollbackEngine
 (Hash-Bound)      (16 Prechecks)      (DryRun / Auth)       (Closed-Loop)        (Restoration)
```

---

## 2. Approval Lifecycle

Operational execution requires formal operator authorization bound to a cryptographic SHA-256 hash of the `ExecutionPlan`.

- `PENDING_APPROVAL`: Approval requested, awaiting operator decision.
- `APPROVED`: Operator authorized exact execution plan hash.
- `REJECTED`: Operator denied execution.
- `EXPIRED`: Request exceeded validity window (default 15 mins).
- `INVALIDATED`: Execution plan parameters modified after approval request; new approval required.
- `CANCELLED`: Operator manually revoked approval.

---

## 3. Execution Safety Model

> [!CAUTION]
> **Strict Anti-Command-Injection Policy**:
> LLMs are **NEVER** permitted to generate or execute arbitrary shell commands, raw SSH strings, router CLI command scripts, firewall rule writes, or SDN controller mutations. All changes must execute through strongly-typed, pre-authorized adapters (`IExecutionAdapter`) accepting only validated parameters.

---

## 4. Dry-Run Mode (`DryRunExecutionAdapter`)

Default execution adapter used for dry-run simulation and development testing:
- Validates targets and parameter schemas.
- Simulates state transitions (`SIMULATED_SUCCESS`).
- Produces execution evidence without altering physical network equipment.

---

## 5. Authorized Adapter Model (`AuthorizedNetworkAdapter`)

Boundary interface for enterprise network integrations:
- Defaults to `NOT_CONFIGURED` state.
- Accepts typed actions only (`FAILOVER_PROVIDER`, `FAILBACK_PROVIDER`, `ENABLE_BACKUP_PATH`, `DISABLE_DEGRADED_PATH`).
- Masks all credentials and secrets before returning event payloads or logs.

---

## 6. Pre-Execution Validation (16 Safety Checks)

Evaluated immediately prior to execution:
1. Trust decision is valid (`NOT BLOCKED`).
2. Path decision is current.
3. Telemetry is fresh ($\le 60$s).
4. Target path exists.
5. Target provider is healthy ($\ge 60.0$).
6. Current path is degraded.
7. Alternate path is superior.
8. Topology is unchanged.
9. Blast radius within policy limit.
10. Required approval exists.
11. Approval is unexpired.
12. Plan hash matches approval.
13. Rollback plan exists.
14. Execution adapter is authorized.
15. Runtime is healthy.
16. No conflicting incident state exists.

---

## 7. Closed-Loop Verification

`PostExecutionVerifier` collects fresh telemetry after execution and compares Before vs After vs Expected metrics:
- Latency ($\le$ max expected)
- Packet Loss ($\le$ max expected)
- Link Utilization ($\le$ max expected)
- Predicted Failure Risk ($\le$ max expected)

Calculates `VerificationResult` containing verification confidence and status (`PASSED` vs `FAILED`).

---

## 8. Automatic Rollback Engine (`RollbackEngine`)

Triggered automatically when post-execution verification fails or performance degrades:
1. Executes inverse rollback steps.
2. Collects fresh telemetry to verify restoration.
3. If restored: sets status to `ROLLED_BACK`.
4. If restoration fails: sets status to `ROLLBACK_FAILED` and raises **CRITICAL OPERATOR ESCALATION**.

---

## 9. Idempotency & Anti-Replay Protection

- Each `ExecutionPlan` hash is recorded in `ApprovalManager._executed_plan_hashes`.
- If an executed plan hash is submitted again, `FailoverService` returns the existing result without re-running execution.

---

## 10. Audit Logging

Append-only execution history is stored locally in air-gapped `data/telemetry.db` (`failover_audit` table), generating unique audit references (`AUDIT-XXXXXXXX`) for every run.

---

## 11. Cross-Platform Behavior

- **Windows Native**: Uses local Ollama GPU acceleration (`http://127.0.0.1:11434`).
- **Linux Native**: Uses local Ollama CPU/GPU backend.
- **VirtualBox Kali Guest**: Automatically detects VirtualBox gateway and routes inference to Windows Host GPU (`http://10.0.2.2:11434`).

---

## 12. Security Boundaries

- Zero unmasked credential logging.
- Anti-replay cryptographic plan hashing.
- No direct SSH or shell command execution by LLMs.
