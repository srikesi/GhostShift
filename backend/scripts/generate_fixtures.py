"""Regenerate the deterministic, simulated telemetry fixtures.

    uv run python scripts/generate_fixtures.py

Every value written here is SIMULATED. The degradation shapes are chosen to be
physically plausible (accelerating fan-bearing vibration, near-linear thermal
drift from oil-cooler fouling) but they are not recorded data-center data.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "ghostshift" / "fixtures" / "telemetry"
START = datetime(2026, 10, 19, 6, 0, tzinfo=timezone.utc)
INTERVAL = timedelta(minutes=15)
N = 240


def daily(i: int, amplitude: float, phase: float = 0.0) -> float:
    hours = i * 0.25
    return amplitude * math.sin(2 * math.pi * (hours / 24.0) + phase)


def rack07(rng: random.Random) -> list[dict]:
    """Mainframe rack: rear cooling-fan-tray bearings wearing out from sample 140."""
    rows = []
    onset = 140
    for i in range(N):
        x = max(0, i - onset)
        vib_deg = 0.239 * (math.exp(0.025 * x) - 1) if x else 0.0
        temp_deg = 0.8 * (math.exp(0.022 * max(0, i - 160)) - 1) if i > 160 else 0.0
        load = 0.03 * math.sin(2 * math.pi * i / 32)  # 8 h IT-load cycle
        rows.append(
            {
                "fan_vibration": 1.55 + load + rng.gauss(0, 0.06) + vib_deg,
                "fan_bearing_temp": 38.5 + daily(i, 0.6) + rng.gauss(0, 0.35) + temp_deg,
                "fan_motor_current": 14.2 + 4 * load + rng.gauss(0, 0.22) + 0.18 * vib_deg,
                "fan_speed": 1450 + 0.18125 * rng.gauss(0, 120),
                "chw_supply_pressure": 6.8 + rng.gauss(0, 0.07),
                "filter_dp": 30 * (3.8 + rng.gauss(0, 0.28)),
            }
        )
    # Two dropped samples to exercise missing-data handling.
    rows[61]["fan_bearing_temp"] = None
    rows[187]["filter_dp"] = None
    return rows


def ch02(rng: random.Random) -> list[dict]:
    """Air-cooled screw chiller: oil cooler fouling from sample 120."""
    rows = []
    onset = 120
    for i in range(N):
        x = max(0, i - onset)
        foul = 0.12 * x + 0.0004 * x * x
        outdoor = 24.0 + daily(i, 2.0, -math.pi / 2) + rng.gauss(0, 0.3)
        rows.append(
            {
                "discharge_temp": 84.0 + 0.35 * (outdoor - 24.0) + rng.gauss(0, 0.5) + foul,
                "oil_temp": 62.0 + 0.3 * (outdoor - 24.0) + rng.gauss(0, 0.45) + 0.85 * foul,
                "condenser_fan_current": 6.2 + rng.gauss(0, 0.09),
                "compressor_motor_current": 128.0 + rng.gauss(0, 1.4) + 0.02 * foul,
                "compressor_vibration": 2.1 + rng.gauss(0, 0.09),
                "outdoor_temp": outdoor,
                "chw_supply_temp": 7.5 + rng.gauss(0, 0.04),
            }
        )
    return rows


def rack07_energy_coolant(rows: list[dict], rng: random.Random) -> None:
    """Fan power and coolant-loop channels (rear-door pressure and reservoir level). Separate RNG so the channels above are unchanged."""
    onset = 140
    for i, row in enumerate(rows):
        x = max(0, i - onset)
        vib_deg = 0.239 * (math.exp(0.025 * x) - 1) if x else 0.0
        load = 0.03 * math.sin(2 * math.pi * i / 32)
        hours_since_refill = (i * 0.25) % 24  # reservoir topped up once a day
        row["fan_power"] = 7.5 + 40 * load + rng.gauss(0, 0.25) + 0.25 * vib_deg
        row["humidifier_water_pressure"] = 2.2 + 0.08 * math.sin(2 * math.pi * i / 8) + rng.gauss(0, 0.03)
        row["humidifier_level"] = 80.0 - 0.4 * hours_since_refill + rng.gauss(0, 0.3)


def ch02_energy_lube(rows: list[dict], rng: random.Random) -> None:
    onset = 120
    for i, row in enumerate(rows):
        x = max(0, i - onset)
        foul = 0.12 * x + 0.0004 * x * x
        row["compressor_power"] = 2 * (62.0 + 0.3 * (row["outdoor_temp"] - 24.0) + rng.gauss(0, 0.6) + 0.03 * foul)
        row["oil_separator_dp"] = 0.35 + rng.gauss(0, 0.01)
        row["oil_level"] = 85.0 + rng.gauss(0, 0.4)


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
    rack = rack07(random.Random(7))
    rack07_energy_coolant(rack, random.Random(107))
    write("MF-07", rack)
    ch = ch02(random.Random(2))
    ch02_energy_lube(ch, random.Random(102))
    write("CH-02", ch)
