import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import time
import os
from config.settings import DB_PATH, ENGINE_PORT, COPILOT_PORT, DEVICE_REGISTRY, DEVICE_NAMES


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Air-Gapped Predictive NOC Copilot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom premium styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* Dark theme overrides */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #f8fafc;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Premium Header */
    .header-card {
        background: rgba(30, 41, 59, 0.7);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 16px;
        padding: 20px 28px;
        margin-bottom: 16px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
        display: flex;
        align-items: center;
        gap: 20px;
    }
    .header-title {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        line-height: 1.2;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 0.92rem;
        margin-top: 4px;
    }

    /* Device badge shown in header */
    .device-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(56, 189, 248, 0.1);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 8px;
        padding: 4px 12px;
        font-size: 0.82rem;
        color: #38bdf8;
        white-space: nowrap;
    }
    .device-badge-type {
        color: #94a3b8;
        font-size: 0.78rem;
    }

    /* Fleet overview row */
    .fleet-row {
        display: flex;
        gap: 10px;
        margin-bottom: 18px;
        flex-wrap: wrap;
    }
    .fleet-card {
        flex: 1;
        min-width: 140px;
        background: rgba(15, 23, 42, 0.65);
        border-radius: 12px;
        padding: 12px 14px;
        border: 1px solid rgba(255,255,255,0.04);
        cursor: pointer;
        transition: border-color 0.2s, box-shadow 0.2s;
    }
    .fleet-card:hover {
        border-color: rgba(56, 189, 248, 0.3);
        box-shadow: 0 0 12px rgba(56, 189, 248, 0.08);
    }
    .fleet-card.selected {
        border-color: rgba(129, 140, 248, 0.5);
        box-shadow: 0 0 18px rgba(129, 140, 248, 0.15);
    }
    .fleet-name {
        font-size: 0.88rem;
        font-weight: 700;
        color: #e2e8f0;
        margin-bottom: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .fleet-type {
        font-size: 0.75rem;
        color: #64748b;
        margin-bottom: 8px;
    }
    .fleet-pill {
        display: inline-block;
        border-radius: 999px;
        padding: 2px 8px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .pill-healthy  { background: rgba(5,150,105,0.18); color: #34d399; border: 1px solid rgba(52,211,153,0.3); }
    .pill-warning  { background: rgba(217,119,6,0.18);  color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
    .pill-critical { background: rgba(220,38,38,0.18);  color: #f87171; border: 1px solid rgba(248,113,113,0.3); }
    .pill-offline  { background: rgba(100,116,139,0.18); color: #94a3b8; border: 1px solid rgba(148,163,184,0.2); }
    .fleet-util {
        font-size: 0.78rem;
        color: #64748b;
        margin-top: 4px;
    }

    /* Metric Cards */
    .metric-container {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        padding: 14px 10px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-value {
        font-size: 1.7rem;
        font-weight: 700;
        color: #f1f5f9;
        margin: 4px 0;
    }
    .metric-label {
        font-size: 0.78rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Risk Banner System */
    .risk-banner {
        border-radius: 12px;
        padding: 18px 20px;
        text-align: center;
        font-weight: 700;
        margin-bottom: 16px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
    }
    .risk-healthy  { background: linear-gradient(135deg,#065f46,#047857); border: 1px solid #059669; color: #ecfdf5; }
    .risk-warning  { background: linear-gradient(135deg,#78350f,#b45309); border: 1px solid #d97706; color: #fef3c7; }
    .risk-alert    { background: linear-gradient(135deg,#7f1d1d,#b91c1c); border: 1px solid #dc2626; color: #fef2f2;
                     animation: pulse 2.0s infinite alternate; }

    @keyframes pulse {
        0%   { box-shadow: 0 0 10px rgba(220,38,38,0.4); }
        100% { box-shadow: 0 0 25px rgba(220,38,38,0.7); }
    }

    /* Copilot Card */
    .copilot-card {
        background: rgba(30, 41, 59, 0.75);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(129, 140, 248, 0.2);
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
    }
    .copilot-section-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: #818cf8;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        padding-bottom: 6px;
        margin-top: 14px;
        margin-bottom: 8px;
    }

    /* Source Cited Tag */
    .source-tag {
        display: inline-block;
        background: rgba(56, 189, 248, 0.15);
        border: 1px solid rgba(56, 189, 248, 0.3);
        color: #38bdf8;
        border-radius: 6px;
        padding: 2px 8px;
        font-size: 0.8rem;
        font-family: monospace;
        margin-right: 8px;
        margin-bottom: 6px;
    }

    /* Device selector styling */
    div[data-testid="stSelectbox"] > div > div {
        background: rgba(15, 23, 42, 0.7) !important;
        border: 1px solid rgba(56, 189, 248, 0.2) !important;
        border-radius: 10px !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper: sim-mode DB access
# ---------------------------------------------------------------------------
def set_sim_mode(mode):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO sim_config (key, value) VALUES ('mode', ?)", (mode,))
        if mode == "congestion":
            cursor.execute("INSERT OR REPLACE INTO sim_config (key, value) VALUES ('congestion_step', '0')")
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Failed to set simulation mode: {e}")


def get_current_sim_mode():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM sim_config WHERE key = 'mode'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "healthy"
    except Exception:
        return "healthy"


# ---------------------------------------------------------------------------
# Helper: fetch risk score for a device (used in fleet overview)
# ---------------------------------------------------------------------------
engine_base = f"http://localhost:{ENGINE_PORT}"
copilot_url = f"http://localhost:{COPILOT_PORT}/copilot"


def fetch_risk(interface_name: str) -> dict | None:
    try:
        r = requests.get(f"{engine_base}/predict",
                         params={"interface": interface_name}, timeout=0.8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Session state — selected device
# ---------------------------------------------------------------------------
if "selected_device_name" not in st.session_state:
    st.session_state.selected_device_name = DEVICE_NAMES[-1]  # default: Branch3-Uplink

# Look up the full device object for the selected name
selected_device = next(
    (d for d in DEVICE_REGISTRY if d["name"] == st.session_state.selected_device_name),
    DEVICE_REGISTRY[-1],
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="header-card">
  <div style="flex:1;">
    <div class="header-title">Air-Gapped Predictive NOC Copilot</div>
    <div class="header-subtitle">Secure MPLS / SD-WAN Network Observability — Zero Outbound Dependency</div>
  </div>
  <div style="display:flex;flex-direction:column;gap:6px;align-items:flex-end;">
    <div class="device-badge">
      📡 <strong>{selected_device['name']}</strong>
    </div>
    <div class="device-badge-type">{selected_device['type']} · {selected_device['location']}</div>
  </div>
</div>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Fleet Overview Row — health pill per device
# ---------------------------------------------------------------------------
fleet_data: dict[str, dict] = {}
for dev in DEVICE_REGISTRY:
    fleet_data[dev["name"]] = fetch_risk(dev["name"]) or {}

def _risk_pill(rd: dict) -> tuple[str, str]:
    """Return (css_class, label) for a fleet health pill."""
    status = rd.get("status", "")
    if status not in ("active",):
        return "pill-offline", "OFFLINE"
    risk = rd.get("risk_score", 0.0)
    if risk < 0.3:
        return "pill-healthy", f"OK {risk*100:.0f}%"
    elif risk < 0.7:
        return "pill-warning", f"WARN {risk*100:.0f}%"
    else:
        return "pill-critical", f"CRIT {risk*100:.0f}%"

fleet_html = '<div class="fleet-row">'
for dev in DEVICE_REGISTRY:
    rd = fleet_data.get(dev["name"], {})
    pill_cls, pill_lbl = _risk_pill(rd)
    util_txt = f"Util: {rd['metrics']['utilization']:.1f}%" if rd.get("metrics") else "—"
    is_sel = "selected" if dev["name"] == selected_device["name"] else ""
    fleet_html += f"""
    <div class="fleet-card {is_sel}">
      <div class="fleet-name" title="{dev['name']}">{dev['name']}</div>
      <div class="fleet-type">{dev['type']}</div>
      <span class="fleet-pill {pill_cls}">{pill_lbl}</span>
      <div class="fleet-util">{util_txt}</div>
    </div>"""
fleet_html += "</div>"
st.markdown(fleet_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Device selector (selectbox, above the split layout)
# ---------------------------------------------------------------------------
sel_col, _ = st.columns([2, 5])
with sel_col:
    chosen = st.selectbox(
        "🔍 Monitor device",
        options=DEVICE_NAMES,
        index=DEVICE_NAMES.index(st.session_state.selected_device_name),
        key="device_selector",
        label_visibility="collapsed",
    )
    if chosen != st.session_state.selected_device_name:
        st.session_state.selected_device_name = chosen
        st.rerun()

selected_name = st.session_state.selected_device_name

# ---------------------------------------------------------------------------
# Fetch predictive data for the selected device
# ---------------------------------------------------------------------------
pred_data = fetch_risk(selected_name)
if pred_data is None:
    st.warning("⚠️ Predictive Engine API offline. Run run.sh to start all backends.")

# ---------------------------------------------------------------------------
# Load telemetry history for the selected device from DB
# ---------------------------------------------------------------------------
db_active = False
df_history = pd.DataFrame()
if os.path.exists(DB_PATH):
    try:
        conn = sqlite3.connect(DB_PATH)
        df_history = pd.read_sql_query("""
            SELECT timestamp, utilization, latency, jitter, drops, routing_flaps
            FROM metrics
            WHERE interface = ?
            ORDER BY timestamp DESC LIMIT 30
        """, conn, params=(selected_name,))
        conn.close()
        if not df_history.empty:
            df_history = df_history.iloc[::-1].reset_index(drop=True)
            db_active = True
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Main layout: charts (left) | risk + copilot (right)
# ---------------------------------------------------------------------------
col_charts, col_info = st.columns([3, 2])

# -------- LEFT COLUMN: Charts & Telemetry --------
with col_charts:
    st.subheader(f"Live Network Telemetry — {selected_name}")

    if db_active:
        latest = df_history.iloc[-1]
        m1, m2, m3, m4, m5 = st.columns(5)
        metrics_def = [
            (m1, "Utilization", f"{latest['utilization']:.1f}%"),
            (m2, "Latency",     f"{latest['latency']:.1f} ms"),
            (m3, "Jitter",      f"{latest['jitter']:.1f} ms"),
            (m4, "Egress Drops",f"{latest['drops']:.1f}/s"),
            (m5, "Route Flaps", str(int(latest['routing_flaps']))),
        ]
        for col, label, value in metrics_def:
            with col:
                st.markdown(f"""
                <div class="metric-container">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                </div>""", unsafe_allow_html=True)

        st.write("")

        def _chart_index(df):
            n = len(df)
            return [f"-{(n-1-i)*2}s" for i in range(n)]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Interface Link Utilization (%)**")
            cdf = df_history[["utilization"]].copy()
            cdf.index = _chart_index(cdf)
            st.area_chart(cdf, color="#0ea5e9", height=220)
        with c2:
            st.markdown("**Round-Trip Latency (ms)**")
            cdf = df_history[["latency"]].copy()
            cdf.index = _chart_index(cdf)
            st.line_chart(cdf, color="#f43f5e", height=220)

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Jitter (ms)**")
            cdf = df_history[["jitter"]].copy()
            cdf.index = _chart_index(cdf)
            st.line_chart(cdf, color="#fbbf24", height=200)
        with c4:
            st.markdown("**Egress Drops (pkts/sec)**")
            cdf = df_history[["drops"]].copy()
            cdf.index = _chart_index(cdf)
            st.area_chart(cdf, color="#a855f7", height=200)
    else:
        st.info(f"Waiting for telemetry data for **{selected_name}**… "
                "Ensure the faultsim daemon is running.")
        st.line_chart(np.random.normal(45, 1, 30))


# -------- RIGHT COLUMN: Risk Banner, Copilot & Controls --------
with col_info:
    st.subheader("Predictive Risk & Copilot")

    # 1. Risk Banner
    if pred_data and pred_data.get("status") == "active":
        risk           = pred_data["risk_score"]
        time_to_impact = pred_data["time_to_impact"]
        signals        = pred_data["contributing_signals"]

        if risk < 0.3:
            banner_class = "risk-healthy"
            status_text  = f"HEALTHY (Risk: {risk*100:.0f}%)"
            desc_text    = "Link parameters are stable. No breach expected."
        elif risk < 0.7:
            banner_class = "risk-warning"
            status_text  = f"WARNING (Risk: {risk*100:.0f}%)"
            desc_text    = f"Early signs of degradation. SLA breach expected in ~{time_to_impact:.1f} min!"
        else:
            banner_class = "risk-alert"
            status_text  = f"CRITICAL ALERT (Risk: {risk*100:.0f}%)"
            desc_text    = f"High probability of SLA breach! ETA: {time_to_impact:.1f} min!"

        st.markdown(f"""
        <div class="risk-banner {banner_class}">
            <div style="font-size:1.35rem;">{status_text}</div>
            <div style="font-size:0.92rem;font-weight:normal;margin-top:6px;">{desc_text}</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="risk-banner risk-healthy">
            <div style="font-size:1.35rem;">NO PREDICTOR STATUS</div>
            <div style="font-size:0.92rem;font-weight:normal;margin-top:6px;">
                Verify that the FastAPI engine is running.
            </div>
        </div>""", unsafe_allow_html=True)
        risk           = 0.0
        time_to_impact = -1.0
        signals        = []

    # 2. AI Copilot Recommendation Card
    if risk >= 0.3 and pred_data:
        st.markdown('<div class="copilot-card">', unsafe_allow_html=True)
        st.markdown("<div style='font-size:1.25rem;font-weight:800;color:#f1f5f9;'>"
                    "🤖 AI Copilot Explanations</div>", unsafe_allow_html=True)

        copilot_response = None
        try:
            payload = {
                "interface":           pred_data["interface"],
                "risk_score":          pred_data["risk_score"],
                "time_to_impact":      pred_data["time_to_impact"],
                "contributing_signals": pred_data["contributing_signals"],
            }
            res = requests.post(copilot_url, json=payload, timeout=9.0)
            if res.status_code == 200:
                copilot_response = res.json()
        except Exception:
            pass

        if copilot_response:
            exp     = copilot_response["explanation"]
            sources = copilot_response.get("sources", [])

            st.markdown('<div class="copilot-section-title">Predicted Issue</div>', unsafe_allow_html=True)
            st.write(exp.get("predicted_issue", "Congestion Detected"))

            c_left, c_right = st.columns(2)
            with c_left:
                st.markdown('<div class="copilot-section-title">Confidence</div>', unsafe_allow_html=True)
                st.write(f"{exp.get('confidence', 0.0)*100:.0f}%")
            with c_right:
                st.markdown('<div class="copilot-section-title">Time to Impact</div>', unsafe_allow_html=True)
                st.write(exp.get("time_to_impact", "Unknown"))

            st.markdown('<div class="copilot-section-title">Affected Scope</div>', unsafe_allow_html=True)
            st.write(exp.get("affected_scope", "Uncertain"))

            st.markdown('<div class="copilot-section-title">Root Cause Hypothesis</div>', unsafe_allow_html=True)
            st.write(exp.get("root_cause_hypothesis", "Uncertain"))

            st.markdown('<div class="copilot-section-title">Recommended Actions</div>', unsafe_allow_html=True)
            for action in exp.get("recommended_actions", []):
                st.markdown(f"- {action}")

            if sources:
                st.markdown('<div class="copilot-section-title">Evidence & Cited Sources (RAG)</div>',
                            unsafe_allow_html=True)
                for src in set(doc["source"] for doc in sources):
                    st.markdown(f'<span class="source-tag">📄 {src}</span>', unsafe_allow_html=True)
                st.write("")
                for doc in sources[:2]:
                    st.markdown(
                        f"<div style='font-size:0.85rem;color:#94a3b8;margin-top:4px;"
                        f"padding-left:8px;border-left:2px solid #38bdf8;'>\"{doc['chunk']}\"</div>",
                        unsafe_allow_html=True)
        else:
            st.write("Loading AI explanation from local model via Ollama…")
            st.spinner()

        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="copilot-card" style="text-align:center;padding:36px 20px;">
            <div style="font-size:4rem;margin-bottom:12px;">🛡️</div>
            <div style="font-size:1.1rem;font-weight:700;color:#f1f5f9;">Network Operations Stable</div>
            <div style="font-size:0.88rem;color:#94a3b8;margin-top:6px;">
                The AI Copilot will automatically analyze anomalies here when predictive risk becomes elevated.
            </div>
        </div>""", unsafe_allow_html=True)

    # 3. Simulation Control Panel
    st.write("")
    st.subheader("Simulation Control Panel")

    current_mode = get_current_sim_mode()
    st.markdown(f"Current mode: **{current_mode.upper()}** · affects all {len(DEVICE_REGISTRY)} devices")

    btn1, btn2, btn3 = st.columns(3)
    with btn1:
        if st.button("Reset to Healthy", use_container_width=True, key="btn_healthy"):
            set_sim_mode("healthy")
            st.rerun()
    with btn2:
        if st.button("Inject Congestion", use_container_width=True, key="btn_congestion"):
            set_sim_mode("congestion")
            st.rerun()
    with btn3:
        if st.button("Apply Mitigation", use_container_width=True, key="btn_mitigate"):
            set_sim_mode("mitigated")
            st.rerun()

# ---------------------------------------------------------------------------
# Auto-refresh every 2 seconds
# ---------------------------------------------------------------------------
time.sleep(2)
st.rerun()
