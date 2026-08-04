import sqlite3
import time
import random
import numpy as np
import os
import sys

DB_PATH = "noc-copilot/data/telemetry.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            timestamp REAL,
            interface TEXT,
            utilization REAL,
            latency REAL,
            jitter REAL,
            drops REAL,
            routing_flaps INTEGER
        )
    """)
    
    # Configuration table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sim_config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert default config
    cursor.execute("INSERT OR IGNORE INTO sim_config (key, value) VALUES ('mode', 'healthy')")
    cursor.execute("INSERT OR IGNORE INTO sim_config (key, value) VALUES ('congestion_step', '0')")
    
    conn.commit()
    conn.close()

def get_sim_config():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM sim_config")
    rows = cursor.fetchall()
    conn.close()
    return dict(rows)

def update_sim_config(key, value):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO sim_config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_latest_metrics(interface):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT utilization, latency, jitter, drops, routing_flaps 
        FROM metrics 
        WHERE interface = ? 
        ORDER BY timestamp DESC LIMIT 1
    """, (interface,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "utilization": row[0],
            "latency": row[1],
            "jitter": row[2],
            "drops": row[3],
            "routing_flaps": row[4]
        }
    return None

def main_loop():
    interface = "Branch3-Uplink"
    print("Starting telemetry simulation daemon...")
    
    # Initial state
    util = 45.0
    lat = 20.0
    jit = 3.0
    drp = 0.0
    flaps = 0
    
    while True:
        try:
            config = get_sim_config()
            mode = config.get("mode", "healthy")
            step = int(config.get("congestion_step", "0"))
            
            # Read latest metric on DB to maintain continuity if daemon restarts
            latest = get_latest_metrics(interface)
            if latest:
                util = latest["utilization"]
                lat = latest["latency"]
                jit = latest["jitter"]
                drp = latest["drops"]
                flaps = latest["routing_flaps"]
                
            if mode == "healthy":
                util = np.clip(util + np.random.normal(0, 0.8), 38.0, 52.0)
                lat = np.clip(lat + np.random.normal(0, 0.4), 16.0, 24.0)
                jit = np.clip(jit + np.random.normal(0, 0.15), 1.5, 4.5)
                drp = 0.0
                flaps = 0
                if random.random() < 0.005:
                    flaps = 1
                    
            elif mode == "congestion":
                step += 1
                update_sim_config("congestion_step", step)
                
                # Ramping up utilization
                util = np.clip(util + 0.3 + np.random.normal(0, 0.4), 35.0, 99.2)
                # Exponential-like ramp in latency
                lat = np.clip(lat + 0.15 * np.exp(step * 0.02) + np.random.normal(0, 0.8), 15.0, 280.0)
                # Jitter increases
                jit = np.clip(jit + 0.06 * np.exp(step * 0.016) + np.random.normal(0, 0.4), 1.0, 28.0)
                # Drops start
                if lat > 75.0:
                    drp = np.clip((lat - 75.0) * 0.12 + np.random.normal(0, 0.3), 0.0, 12.0)
                else:
                    drp = 0.0
                # Routing flaps
                flaps = 0
                if step > 60 and random.random() < 0.06:
                    flaps = random.choice([1, 2])
                    
            elif mode == "mitigated":
                # Rapidly decaying metrics back to healthy base
                util = np.clip(util - 4.0 + np.random.normal(0, 0.5), 45.0, 100.0)
                lat = np.clip(lat - 15.0 + np.random.normal(0, 0.8), 20.0, 300.0)
                jit = np.clip(jit - 2.0 + np.random.normal(0, 0.2), 3.0, 50.0)
                drp = np.clip(drp - 1.5, 0.0, 15.0)
                flaps = 0
                
                # If fully recovered, reset mode back to healthy
                if util <= 52.0 and lat <= 24.0:
                    update_sim_config("mode", "healthy")
                    update_sim_config("congestion_step", "0")
                    print("Simulation recovered and reset to healthy.")
            
            # Insert into database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            timestamp = time.time()
            cursor.execute("""
                INSERT INTO metrics (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, interface, float(util), float(lat), float(jit), float(drp), int(flaps)))
            
            # Clean up old metrics to prevent database bloat (keep last 1 hour of data = 1800 samples)
            cursor.execute("""
                DELETE FROM metrics WHERE timestamp < ?
            """, (timestamp - 3600,))
            
            conn.commit()
            conn.close()
            
            print(f"[{mode.upper()}] Util: {util:.1f}%, Lat: {lat:.1f}ms, Jitter: {jit:.1f}ms, Drops: {drp:.1f}, Flaps: {flaps}")
            
        except Exception as e:
            print(f"Error in simulation loop: {e}", file=sys.stderr)
            
        time.sleep(2)

if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1:
        # CLI commands
        cmd = sys.argv[1]
        if cmd == "congestion":
            update_sim_config("mode", "congestion")
            update_sim_config("congestion_step", "0")
            print("Set simulation mode to congestion.")
        elif cmd == "healthy":
            update_sim_config("mode", "healthy")
            update_sim_config("congestion_step", "0")
            print("Set simulation mode to healthy.")
        elif cmd == "mitigate":
            update_sim_config("mode", "mitigated")
            print("Set simulation mode to mitigated.")
    else:
        # Run daemon
        main_loop()
