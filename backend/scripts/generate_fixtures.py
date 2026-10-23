"""Regenerate the deterministic, simulated telemetry fixtures.

    uv run python scripts/generate_fixtures.py

Every value written here is SIMULATED. The degradation shapes are chosen to be
physically plausible (accelerating bearing vibration, linear-ish thermal drift
from cooler fouling) but they are not recorded plant data.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "faultzy" / "fixtures" / "telemetry"
START = datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)
N = 240


def daily(i: int, amplitude: float, phase: float = 0.0) -> float:
    hours = i * 0.25
    return amplitude * math.sin(2 * math.pi * (hours / 24.0) + phase)


def vmc07(rng: random.Random) -> list[dict]:
    rows = []
    onset = 140
    for i in range(N):
        x = max(0, i - onset)
        vib_deg = 0.239 * (math.exp(0.025 * x) - 1) if x else 0.0
        temp_deg = 0.8 * (math.exp(0.022 * max(0, i - 160)) - 1) if i > 160 else 0.0
        load = 0.03 * math.sin(2 * math.pi * i / 32)  # 8 h production-mix cycle
        rows.append(
            {
                "spindle_vib_rms": 1.55 + load + rng.gauss(0, 0.06) + vib_deg,
                "spindle_bearing_temp": 38.5 + daily(i, 0.6) + rng.gauss(0, 0.35) + temp_deg,
                "spindle_motor_current": 14.2 + 4 * load + rng.gauss(0, 0.22) + 0.18 * vib_deg,
                "spindle_speed": 8000 + rng.gauss(0, 120),
                "coolant_pressure": 6.8 + rng.gauss(0, 0.07),
                "x_following_error": 3.8 + rng.gauss(0, 0.28),
            }
        )
    # Two dropped samples to exercise missing-data handling.
    rows[61]["spindle_bearing_temp"] = None
    rows[187]["x_following_error"] = None
    return rows


def cmp02(rng: random.Random) -> list[dict]:
    rows = []
    onset = 120
    for i in range(N):
        x = max(0, i - onset)
        foul = 0.12 * x + 0.0004 * x * x
        ambient = 24.0 + daily(i, 2.0, -math.pi / 2) + rng.gauss(0, 0.3)
        rows.append(
            {
                "discharge_temp": 84.0 + 0.35 * (ambient - 24.0) + rng.gauss(0, 0.5) + foul,
                "oil_injection_temp": 62.0 + 0.3 * (ambient - 24.0) + rng.gauss(0, 0.45) + 0.85 * foul,
                "cooling_fan_current": 6.2 + rng.gauss(0, 0.09),
                "motor_current": 128.0 + rng.gauss(0, 1.4) + 0.02 * foul,
                "airend_vibration": 2.1 + rng.gauss(0, 0.09),
                "ambient_temp": ambient,
                "discharge_pressure": 7.5 + rng.gauss(0, 0.04),
            }
        )
    return rows


def write(machine_id: str, rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["index", "timestamp", *rows[0].keys()]
    path = OUT / f"{machine_id}.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for i, row in enumerate(rows):
            out = {"index": i, "timestamp": (START + i * INTERVAL).isoformat().replace("+00:00", "Z")}
            for k, v in row.items():
                out[k] = "" if v is None else f"{v:.3f}"
            writer.writerow(out)
    print(f"wrote {path.relative_to(OUT.parents[2])} ({len(rows)} rows)")


if __name__ == "__main__":
    write("VMC-07", vmc07(random.Random(7)))
    write("CMP-02", cmp02(random.Random(2)))
