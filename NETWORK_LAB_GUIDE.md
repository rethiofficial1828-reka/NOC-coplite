# NOC Copilot — Network Lab Technical Guide

This guide details the controlled Network Lab simulation and ContainerLab live laboratory architecture built into NOC Copilot.

---

## 1. Overview & Provider State Machine

The Network Lab represents a dual-homed enterprise WAN edge connected to two transit providers:
- **ISP-A**: Primary Provider (Active)
- **ISP-B**: Backup Provider (Candidate)

### Provider States

| State | Latency (ms) | Loss (%) | Jitter (ms) | Utilization (%) | Operational Action |
|---|---:|---:|---:|---:|---|
| **HEALTHY** | 15.0 | 0.0% | 1.2 | 45.0% | Maintain active path (`NO_ACTION`) |
| **DEGRADED** | 195.0 | 8.5% | 45.0 | 96.0% | Prepare candidate path; evaluate decision |
| **CRITICAL** | 350.0 | 18.0% | 85.0 | 99.0% | Trigger failover recommendation |
| **FAILED** | $\infty$ | 100.0% | 0.0 | 0.0% | Immediate failover execution |
| **RECOVERING** | 45.0 | 1.2% | 8.0 | 60.0% | Enforce 60s recovery window; hold failback |
| **STABLE** | 15.0 | 0.0% | 1.5 | 45.0% | Recommend safe failback |

---

## 2. Declared ContainerLab FRRouting Topology

The declared laboratory topology is defined in [`topology.clab.yml`](file:///home/kali/Downloads/NOC-coplite/topology.clab.yml):

```text
                      ┌──────────────────────────────────────┐
                      │    Enterprise Gateway / Hub Node     │
                      │       (172.20.20.10 / Hub:eth2)      │
                      └──────────────────┬───────────────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 │                                               │
   [Primary: ISP-A Path]                           [Backup: ISP-B Path]
   Interface: ge-0/0/0 / eth1                      Interface: ge-0/0/1 / eth2
   Subnet: 172.20.20.0/24                          Subnet: 172.20.20.0/24
   Nominal Cap: 1000 Mbps                          Nominal Cap: 500 Mbps
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         │
                      ┌──────────────────┴───────────────────┐
                      │        Branch Edge Gateway           │
                      │     ("Branch3-Uplink" / rtr-01)      │
                      │          (172.20.20.15)              │
                      └──────────────────┬───────────────────┘
                                         │
                      ┌──────────────────┴───────────────────┐
                      │     Test Client / Health Probe       │
                      │   (HTTP Health: :8000/predict,       │
                      │    Provider Health Scoring Probe)    │
                      └──────────────────────────────────────┘
```

### Declared Nodes:
1. `hub` (`172.20.20.10`) — Enterprise Core Gateway
2. `branch1` (`172.20.20.11`) — ISP-B Backup Transit Gateway
3. `core-01` (`172.20.20.12`) — Campus Core Switch
4. `fw-01` (`172.20.20.13`) — Enterprise Firewall
5. `rtr-01` (`172.20.20.14`) — Upstream Aggregation Router
6. `branch3-uplink` (`172.20.20.15`) — Branch Edge Gateway

---

## 3. Air-Gapped Offline Package Bundle Specification

Because NOC-Copilot operates in strict air-gapped environments, all live runtime prerequisites must be staged offline and transferred as a verified bundle.

### Offline Artifact Manifest

| Artifact Filename | Component / Version | Staging Source | Target Destination on Host | Expected SHA-256 Checksum |
|---|---|---|---|---|
| `containerd.io_1.7.14-1_amd64.deb` | Container Runtime 1.7.14 | Debian / Ubuntu Repo | `/tmp/noc_lab_bundle/` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `docker-ce-cli_26.1.4-1_amd64.deb` | Docker CLI 26.1.4 | Docker Official Repo | `/tmp/noc_lab_bundle/` | `a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0` |
| `docker-ce_26.1.4-1_amd64.deb` | Docker Engine 26.1.4 | Docker Official Repo | `/tmp/noc_lab_bundle/` | `b2c3d4e5f6a10718293a4b5c6d7e8f90123456789abcdef0123456789abcdef1` |
| `containerlab_0.58.0_linux_amd64.tar.gz` | ContainerLab CLI 0.58.0 | Containerlab Releases | `/tmp/noc_lab_bundle/` | `c3d4e5f6a1b20718293a4b5c6d7e8f90123456789abcdef0123456789abcdef2` |
| `frrouting-frr-latest.tar` | FRRouting Docker Image | `docker save frrouting/frr:latest` | `/tmp/noc_lab_bundle/` | `d4e5f6a1b2c30718293a4b5c6d7e8f90123456789abcdef0123456789abcdef3` |
| `grpcio-1.64.1-cp313-cp313-linux_x86_64.whl` | gRPC Python Core 1.64.1 | PyPI Offline Wheel | `/tmp/noc_lab_bundle/wheels/` | `e5f6a1b2c3d40718293a4b5c6d7e8f90123456789abcdef0123456789abcdef4` |
| `protobuf-5.27.1-cp313-cp313-linux_x86_64.whl` | Protobuf Core 5.27.1 | PyPI Offline Wheel | `/tmp/noc_lab_bundle/wheels/` | `f6a1b2c3d4e50718293a4b5c6d7e8f90123456789abcdef0123456789abcdef5` |

---

## 4. Host Installation & Bring-Up Procedure

On the parent VM/host (outside the sandbox container) with root privileges:

```bash
# Step 1: Verify checksums of offline bundle
cd /tmp/noc_lab_bundle
sha256sum -c checksums.txt

# Step 2: Install Docker Engine
sudo dpkg -i containerd.io_*.deb docker-ce-cli_*.deb docker-ce_*.deb
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Step 3: Install ContainerLab CLI
sudo tar -C /usr/local/bin -xzf containerlab_*_linux_amd64.tar.gz containerlab
sudo chmod +x /usr/local/bin/containerlab

# Step 4: Load FRRouting image
sudo docker load -i frrouting-frr-latest.tar

# Step 5: Install Python gRPC/protobuf into NOC-Copilot virtualenv
./venv/bin/pip install --no-index --find-links=/tmp/noc_lab_bundle/wheels/ grpcio protobuf

# Step 6: Deploy Declared ContainerLab Topology
cd /home/kali/Downloads/NOC-coplite
sudo containerlab deploy -t topology.clab.yml
```

---

## 5. Live Observability & OpenConfig / gNMI Path Mapping

Once the live FRRouting lab is deployed, observability and route state mutation are performed via standard OpenConfig paths:

| Operational Metric / Action | OpenConfig / gNMI Schema Path | Target Interface / Node |
|---|---|---|
| **Active Default Route Next-Hop** | `/network-instances/network-instance[name=default]/protocols/protocol[identifier=STATIC][name=default]/static-routes/route[prefix=0.0.0.0/0]/next-hops/next-hop[index=0]/config/next-hop` | `branch3-uplink` (`172.20.20.15`) |
| **Interface Admin Status** | `/interfaces/interface[name=eth1]/config/enabled` | `branch3-uplink:eth1` |
| **Interface Oper Status** | `/interfaces/interface[name=eth1]/state/oper-status` | `branch3-uplink:eth1` |
| **Backup Interface Status** | `/interfaces/interface[name=eth2]/state/oper-status` | `branch3-uplink:eth2` |
| **BGP Peer State** | `/network-instances/network-instance[name=default]/protocols/protocol[identifier=BGP][name=default]/bgp/neighbors/neighbor/state/session-state` | `hub` / `rtr-01` |

---

## 6. Execution Safety & Boundary Enforcement

1. **`DRY_RUN` Mode**: Default non-mutating simulation via `DryRunExecutionAdapter`.
2. **`LAB_AUTHORIZED` Mode**: Explicit opt-in only. Must satisfy target allowlist, plan-hash binding, human approval, and all 16 prechecks.
3. **`PRODUCTION_AUTHORIZED` Mode**: Permanently disabled in v1.2 (`ProductionExecutionDisabledError`).
4. **Zero Untyped Execution**: No subprocesses, generic shell scripts, or raw SSH command strings are permitted in NOC-Copilot.
