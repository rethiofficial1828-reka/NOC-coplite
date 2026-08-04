import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import time
import os

# Page config
st.set_page_config(
    page_title="Air-Gapped Predictive NOC Copilot",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom premium styling
st.markdown("""
<style>
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
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
    }
    .header-title {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 1rem;
        margin-top: 4px;
    }
    
    /* Metric Cards */
    .metric-container {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #f1f5f9;
        margin: 4px 0;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    /* Risk Banner System */
    .risk-banner {
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        font-weight: 700;
        margin-bottom: 20px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
        transition: all 0.3s ease;
    }
    .risk-healthy {
        background: linear-gradient(135deg, #065f46 0%, #047857 100%);
        border: 1px solid #059669;
        color: #ecfdf5;
    }
    .risk-warning {
        background: linear-gradient(135deg, #78350f 0%, #b45309 100%);
        border: 1px solid #d97706;
        color: #fef3c7;
    }
    .risk-alert {
        background: linear-gradient(135deg, #7f1d1d 0%, #b91c1c 100%);
        border: 1px solid #dc2626;
        color: #fef2f2;
        animation: pulse 2.0s infinite alternate;
    }
    
    @keyframes pulse {
        0% { box-shadow: 0 0 10px rgba(220, 38, 38, 0.4); }
        100% { box-shadow: 0 0 25px rgba(220, 38, 38, 0.7); }
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
        font-size: 1.1rem;
        font-weight: 700;
        color: #818cf8;
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        padding-bottom: 6px;
        margin-top: 16px;
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
</style>
""", unsafe_allow_html=True)

# Helper function to write database config
def set_sim_mode(mode):
    try:
        conn = sqlite3.connect("noc-copilot/data/telemetry.db")
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
        conn = sqlite3.connect("noc-copilot/data/telemetry.db")
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM sim_config WHERE key = 'mode'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "healthy"
    except Exception:
        return "healthy"

# Header
st.markdown("""
<div class="header-card">
    <div class="header-title">Air-Gapped Predictive NOC Copilot</div>
    <div class="header-subtitle">Secure MPLS / SD-WAN Network Observability — Zero Outbound Dependency</div>
</div>
""", unsafe_allow_html=True)

# Layout division
col_charts, col_info = st.columns([3, 2])

# Query Predictive Engine API
engine_url = "http://localhost:8000/predict"
copilot_url = "http://localhost:8001/copilot"

pred_data = None
try:
    response = requests.get(engine_url, params={"interface": "Branch3-Uplink"}, timeout=1.0)
    if response.status_code == 200:
        pred_data = response.json()
except Exception as e:
    st.warning("⚠️ Predictive Engine API offline. Run run.sh to start all backends.")

# Extract current metrics & data history from database for plotting
db_active = False
df_history = pd.DataFrame()
if os.path.exists("noc-copilot/data/telemetry.db"):
    try:
        conn = sqlite3.connect("noc-copilot/data/telemetry.db")
        df_history = pd.read_sql_query("""
            SELECT timestamp, utilization, latency, jitter, drops, routing_flaps 
            FROM metrics 
            WHERE interface = 'Branch3-Uplink' 
            ORDER BY timestamp DESC LIMIT 30
        """, conn)
        conn.close()
        if not df_history.empty:
            df_history = df_history.iloc[::-1].reset_index(drop=True)
            db_active = True
    except Exception as e:
        pass

# ----------------- LEFT COLUMN: Charts & Telemetry -----------------
with col_charts:
    st.subheader("Live Network Telemetry (Branch3-Uplink)")
    
    if db_active:
        # Mini metrics row
        latest = df_history.iloc[-1]
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Utilization</div>
                <div class="metric-value">{latest['utilization']:.1f}%</div>
            </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Latency</div>
                <div class="metric-value">{latest['latency']:.1f} ms</div>
            </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Jitter</div>
                <div class="metric-value">{latest['jitter']:.1f} ms</div>
            </div>
            """, unsafe_allow_html=True)
        with m4:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Egress Drops</div>
                <div class="metric-value">{latest['drops']:.1f}/s</div>
            </div>
            """, unsafe_allow_html=True)
        with m5:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Route Flaps</div>
                <div class="metric-value">{int(latest['routing_flaps'])}</div>
            </div>
            """, unsafe_allow_html=True)
            
        st.write("")
        
        # Plot time-series charts
        # Utilization and Latency charts side by side
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Interface Link Utilization (%)**")
            chart_df = df_history[["utilization"]].copy()
            # Map index to elapsed seconds (2s intervals)
            chart_df.index = [f"-{(len(chart_df)-1-i)*2}s" for i in range(len(chart_df))]
            st.area_chart(chart_df, color="#0ea5e9", height=220)
        with c2:
            st.markdown("**Round-Trip Latency (ms)**")
            chart_df = df_history[["latency"]].copy()
            chart_df.index = [f"-{(len(chart_df)-1-i)*2}s" for i in range(len(chart_df))]
            st.line_chart(chart_df, color="#f43f5e", height=220)
            
        # Jitter and Drops
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("**Jitter (ms)**")
            chart_df = df_history[["jitter"]].copy()
            chart_df.index = [f"-{(len(chart_df)-1-i)*2}s" for i in range(len(chart_df))]
            st.line_chart(chart_df, color="#fbbf24", height=200)
        with c4:
            st.markdown("**Egress Drops (pkts/sec)**")
            chart_df = df_history[["drops"]].copy()
            chart_df.index = [f"-{(len(chart_df)-1-i)*2}s" for i in range(len(chart_df))]
            st.area_chart(chart_df, color="#a855f7", height=200)
    else:
        st.info("Waiting for telemetry database metrics... Ensure the faultsim daemon is running.")
        # Dummy charts for UI preview when database is cold
        st.line_chart(np.random.normal(45, 1, 30))

# ----------------- RIGHT COLUMN: Risk Banner, Copilot & Controls -----------------
with col_info:
    st.subheader("Predictive Risk & Copilot")
    
    # 1. Show Risk Banner
    if pred_data and pred_data.get("status") == "active":
        risk = pred_data["risk_score"]
        time_to_impact = pred_data["time_to_impact"]
        signals = pred_data["contributing_signals"]
        
        if risk < 0.3:
            banner_class = "risk-healthy"
            status_text = f"HEALTHY (Risk: {risk*100:.0f}%)"
            desc_text = "Primary MPLS link parameters are stable. No breach expected."
        elif risk < 0.7:
            banner_class = "risk-warning"
            status_text = f"WARNING (Risk: {risk*100:.0f}%)"
            desc_text = f"Early signs of degradation. SLA breach expected in ~{time_to_impact:.1f} minutes!"
        else:
            banner_class = "risk-alert"
            status_text = f"CRITICAL ALERT (Risk: {risk*100:.0f}%)"
            desc_text = f"High probability of SLA breach! Estimated time-to-impact: {time_to_impact:.1f} minutes!"
            
        st.markdown(f"""
        <div class="risk-banner {banner_class}">
            <div style="font-size: 1.4rem;">{status_text}</div>
            <div style="font-size: 0.95rem; font-weight: normal; margin-top: 6px;">{desc_text}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="risk-banner risk-healthy">
            <div style="font-size: 1.4rem;">NO PREDICTOR STATUS</div>
            <div style="font-size: 0.95rem; font-weight: normal; margin-top: 6px;">Verify that the FastAPI engine is running.</div>
        </div>
        """, unsafe_allow_html=True)
        risk = 0.0
        time_to_impact = -1.0
        signals = []

    # 2. Copilot Recommendation Card
    if risk >= 0.3 and pred_data:
        st.markdown('<div class="copilot-card">', unsafe_allow_html=True)
        st.markdown("<div style='font-size: 1.3rem; font-weight: 800; color: #f1f5f9; display: flex; align-items: center;'>🤖 AI Copilot Explanations</div>", unsafe_allow_html=True)
        
        # Trigger /copilot API
        copilot_response = None
        try:
            copilot_payload = {
                "interface": pred_data["interface"],
                "risk_score": pred_data["risk_score"],
                "time_to_impact": pred_data["time_to_impact"],
                "contributing_signals": pred_data["contributing_signals"]
            }
            # Retrieve with timeout
            copilot_res = requests.post(copilot_url, json=copilot_payload, timeout=9.0)
            if copilot_res.status_code == 200:
                copilot_response = copilot_res.json()
        except Exception:
            pass
            
        if copilot_response:
            exp = copilot_response["explanation"]
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
                
            # Render Cited Sources
            if sources:
                st.markdown('<div class="copilot-section-title">Evidence & Cited Sources (RAG)</div>', unsafe_allow_html=True)
                unique_srcs = set(doc["source"] for doc in sources)
                for src in unique_srcs:
                    st.markdown(f'<span class="source-tag">📄 {src}</span>', unsafe_allow_html=True)
                st.write("")
                for idx, doc in enumerate(sources[:2]):
                    st.markdown(f"<div style='font-size: 0.85rem; color: #94a3b8; margin-top: 4px; padding-left: 8px; border-left: 2px solid #38bdf8;'>\"{doc['chunk']}\"</div>", unsafe_allow_html=True)
        else:
            st.write("Loading AI explanation from local Phi-3 via Ollama...")
            st.spinner()
            
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        # Under normal conditions, show healthy status
        st.markdown("""
        <div class="copilot-card" style="text-align: center; padding: 36px 20px;">
            <div style="font-size: 4rem; margin-bottom: 12px;">🛡️</div>
            <div style="font-size: 1.15rem; font-weight: 700; color: #f1f5f9;">Network Operations Stable</div>
            <div style="font-size: 0.9rem; color: #94a3b8; margin-top: 6px;">The AI Copilot will automatically analyze and explain anomalies here if predictive risk becomes elevated.</div>
        </div>
        """, unsafe_allow_html=True)

    # 3. Interactive Scenario Controls
    st.write("")
    st.subheader("Simulation Control Panel")
    
    current_mode = get_current_sim_mode()
    st.markdown(f"Current mode: **{current_mode.upper()}**")
    
    btn1, btn2, btn3 = st.columns(3)
    with btn1:
        if st.button("Reset to Healthy", use_container_width=True):
            set_sim_mode("healthy")
            st.rerun()
    with btn2:
        if st.button("Inject Congestion", use_container_width=True):
            set_sim_mode("congestion")
            st.rerun()
    with btn3:
        if st.button("Apply Mitigation", use_container_width=True):
            set_sim_mode("mitigated")
            st.rerun()

# Auto rerun every 2 seconds to keep metrics updated
time.sleep(2)
st.rerun()
