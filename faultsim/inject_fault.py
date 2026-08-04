import sqlite3
import time
import random
import numpy as np
import os
import sys

from config.settings import DB_PATH, DEVICE_REGISTRY


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
            "routing_flaps": row[4],
        }
    return None


# ---------------------------------------------------------------------------
# Per-device baseline offsets so each device produces a distinct telemetry
# profile even though they share the same global simulation mode.
# Offsets are deterministic (keyed by device id) for reproducibility.
# ---------------------------------------------------------------------------
_DEVICE_BASELINES = {
    "core-01":        {"util": 60.0, "lat": 5.0,  "jit": 1.5,  "util_range": (55.0, 70.0), "lat_range": (3.0, 8.0)},
    "fw-01":          {"util": 50.0, "lat": 12.0, "jit": 2.0,  "util_range": (44.0, 58.0), "lat_range": (9.0, 16.0)},
    "rtr-01":         {"util": 42.0, "lat": 18.0, "jit": 2.8,  "util_range": (36.0, 50.0), "lat_range": (14.0, 22.0)},
    "branch3-uplink": {"util": 45.0, "lat": 20.0, "jit": 3.0,  "util_range": (38.0, 52.0), "lat_range": (16.0, 24.0)},
}


def _init_device_state():
    """Build initial state dict for every registered device."""
    states = {}
    for device in DEVICE_REGISTRY:
        did = device["id"]
        bl = _DEVICE_BASELINES.get(did, {"util": 45.0, "lat": 20.0, "jit": 3.0,
                                         "util_range": (38.0, 52.0), "lat_range": (16.0, 24.0)})
        # Try to resume from latest DB row so a daemon restart is seamless
        latest = get_latest_metrics(device["name"])
        if latest:
            states[did] = {
                "util": latest["utilization"],
                "lat":  latest["latency"],
                "jit":  latest["jitter"],
                "drp":  latest["drops"],
                "flaps": latest["routing_flaps"],
            }
        else:
            states[did] = {
                "util": bl["util"],
                "lat":  bl["lat"],
                "jit":  bl["jit"],
                "drp":  0.0,
                "flaps": 0,
            }
    return states


def _step_device(device_id, state, mode, step):
    """Advance one telemetry tick for a single device under the given mode."""
    bl = _DEVICE_BASELINES.get(device_id, {
        "util": 45.0, "lat": 20.0, "jit": 3.0,
        "util_range": (38.0, 52.0), "lat_range": (16.0, 24.0),
    })
    util_lo, util_hi = bl["util_range"]
    lat_lo,  lat_hi  = bl["lat_range"]

    util  = state["util"]
    lat   = state["lat"]
    jit   = state["jit"]
    drp   = state["drp"]
    flaps = state["flaps"]

    if mode == "healthy":
        util  = np.clip(util  + np.random.normal(0, 0.8),  util_lo, util_hi)
        lat   = np.clip(lat   + np.random.normal(0, 0.4),  lat_lo,  lat_hi)
        jit   = np.clip(jit   + np.random.normal(0, 0.15), 1.5, 4.5)
        drp   = 0.0
        flaps = 0
        if random.random() < 0.005:
            flaps = 1

    elif mode == "congestion":
        # Ramp up — each device degrades at a slightly different rate
        rate = _DEVICE_BASELINES.get(device_id, {}).get("util", 45.0) / 45.0  # ~1.0–1.3
        util = np.clip(util + (0.3 * rate) + np.random.normal(0, 0.4), util_lo - 5, 99.2)
        lat  = np.clip(lat  + 0.15 * np.exp(step * 0.02) * rate + np.random.normal(0, 0.8), lat_lo, 280.0)
        jit  = np.clip(jit  + 0.06 * np.exp(step * 0.016) * rate + np.random.normal(0, 0.4), 1.0, 28.0)
        drp  = np.clip((lat - 75.0) * 0.12 + np.random.normal(0, 0.3), 0.0, 12.0) if lat > 75.0 else 0.0
        flaps = 0
        if step > 60 and random.random() < 0.06:
            flaps = random.choice([1, 2])

    elif mode == "mitigated":
        util  = np.clip(util  - 4.0 + np.random.normal(0, 0.5),  util_lo, 100.0)
        lat   = np.clip(lat   - 15.0 + np.random.normal(0, 0.8), lat_lo,  300.0)
        jit   = np.clip(jit   - 2.0 + np.random.normal(0, 0.2),  bl["jit"], 50.0)
        drp   = np.clip(drp   - 1.5, 0.0, 15.0)
        flaps = 0

    return {"util": util, "lat": lat, "jit": jit, "drp": drp, "flaps": flaps}


def main_loop():
    print(f"Starting multi-device telemetry simulation daemon "
          f"({len(DEVICE_REGISTRY)} devices)...")
    for dev in DEVICE_REGISTRY:
        print(f"  • {dev['name']} [{dev['type']}] — {dev['location']}")

    states = _init_device_state()

    while True:
        try:
            config = get_sim_config()
            mode   = config.get("mode", "healthy")
            step   = int(config.get("congestion_step", "0"))

            if mode == "congestion":
                step += 1
                update_sim_config("congestion_step", step)

            timestamp = time.time()
            conn   = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            all_recovered = True

            for device in DEVICE_REGISTRY:
                did  = device["id"]
                name = device["name"]

                # Advance state
                states[did] = _step_device(did, states[did], mode, step)
                s = states[did]

                cursor.execute("""
                    INSERT INTO metrics
                        (timestamp, interface, utilization, latency, jitter, drops, routing_flaps)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (timestamp, name,
                      float(s["util"]), float(s["lat"]), float(s["jit"]),
                      float(s["drp"]), int(s["flaps"])))

                if mode == "mitigated":
                    bl = _DEVICE_BASELINES.get(did, {})
                    _, util_hi = bl.get("util_range", (38.0, 52.0))
                    _, lat_hi  = bl.get("lat_range",  (16.0, 24.0))
                    if s["util"] > util_hi or s["lat"] > lat_hi:
                        all_recovered = False

                print(f"[{mode.upper()}] {name}: "
                      f"Util={s['util']:.1f}% Lat={s['lat']:.1f}ms "
                      f"Jit={s['jit']:.1f}ms Drp={s['drp']:.1f} Flaps={s['flaps']}")

            # Prune rows older than 1 hour (keep last 1800 samples per device)
            cursor.execute("DELETE FROM metrics WHERE timestamp < ?", (timestamp - 3600,))
            conn.commit()
            conn.close()

            # Auto-recover from mitigated mode once all devices are back to baseline
            if mode == "mitigated" and all_recovered:
                update_sim_config("mode", "healthy")
                update_sim_config("congestion_step", "0")
                print("All devices recovered — simulation reset to healthy.")

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
