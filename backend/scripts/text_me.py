"""Trigger a fault and report the technician text (and its link) from a running API.

    make api       # in one terminal, with your .env loaded
    make text-me   # in another

To receive a real SMS, set in `.env` (repo root) and restart the API:
    GHOSTSHIFT_MODE=auto
    GHOSTSHIFT_SMS_PROVIDER=twilio
    TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... TWILIO_FROM_NUMBER=+1...
    GHOSTSHIFT_DEMO_TECHNICIAN_PHONE=+1...        # your phone
    GHOSTSHIFT_PUBLIC_BASE_URL=http://<address your phone can open>:5173
Without these, the text is recorded (simulated) and the link is printed here instead.
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

API = os.environ.get("GHOSTSHIFT_API_URL", "http://127.0.0.1:8000")
FAULT_STEPS = {"VMC-07": [172, 216], "CMP-02": [150]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", default="VMC-07", choices=sorted(FAULT_STEPS))
    args = ap.parse_args()
    c = httpx.Client(base_url=API, timeout=30)
    try:
        health = c.get("/api/health").json()
    except httpx.HTTPError:
        print(f"API not reachable at {API}. Start it with `make api`.")
        return 1

    sms = next(p for p in health["providers"] if p["capability"] == "sms")
    print(f"Mode: {health['mode']} · SMS: {sms['provider']['name']} ({sms['detail']})")

    c.post("/api/demo/reset")
    incident_id = None
    for cursor in FAULT_STEPS[args.machine]:
        r = c.post(f"/api/machines/{args.machine}/replay", json={"action": "seek", "cursor": cursor}).json()
        incident_id = r["triggered_incident_id"] or incident_id
    if not incident_id:
        print("No problem was flagged; nothing to text.")
        return 1

    notes = c.get(f"/api/notifications?incident_id={incident_id}").json()
    if not notes:
        print(f"{incident_id} opened, but its priority does not require a text.")
        return 1
    n = notes[-1]
    print(f"\nTo:     {n['recipient_label']} {n['to_masked']}")
    print(f"Status: {n['status']}" + (f" ({n['error']})" if n["error"] else ""))
    print(f"Text:   {n['body']}")
    print(f"\nOpen the technician view: {n['inspection_url']}")
    if n["status"] == "simulated_sent":
        print("\nThis text was recorded, not sent. See the top of this script for the settings that send it for real.")
    if "localhost" in n["inspection_url"] or "127.0.0.1" in n["inspection_url"]:
        print("Note: a phone cannot open a localhost link. Set GHOSTSHIFT_PUBLIC_BASE_URL to a reachable address.")
    return 0 if n["status"] in ("sent", "simulated_sent") else 2


if __name__ == "__main__":
    sys.exit(main())
