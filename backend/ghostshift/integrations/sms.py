"""SMS delivery: deterministic stub and Twilio REST adapter."""

from __future__ import annotations

import time
from typing import Callable

import httpx

from ..schemas.common import ProviderKind
from .base import ProviderHealth, SmsResult, info


class SimulatedSms:
    """Records messages in memory. Nothing leaves the process."""

    info = info("sms-simulated", ProviderKind.stub)

    def __init__(self):
        self.outbox: list[dict] = []

    def send(self, *, to: str, body: str) -> SmsResult:
        self.outbox.append({"to": to, "body": body})
        return SmsResult(delivered=True, simulated=True, attempts=1, external_id=f"SIM-SMS-{len(self.outbox):04d}")

    def health(self) -> ProviderHealth:
        return ProviderHealth(capability="sms", provider=self.info, configured=True, available=True,
                              detail="Simulated: messages are recorded, not sent")


class TwilioSms:
    """Twilio Programmable Messaging via REST (no SDK dependency).

    Real delivery is opt-in: the recipient is always `override_to`
    (GHOSTSHIFT_DEMO_TECHNICIAN_PHONE). Fixture phone numbers are never dialled.
    """

    API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(
        self,
        *,
        account_sid: str | None,
        auth_token: str | None,
        from_number: str | None,
        override_to: str | None,
        max_attempts: int = 3,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._sid = account_sid
        self._token = auth_token
        self._from = from_number
        self._override_to = override_to
        self._max_attempts = max_attempts
        self._transport = transport
        self._sleep = sleep
        self.info = info("twilio", ProviderKind.external)

    @property
    def configured(self) -> bool:
        return bool(self._sid and self._token and self._from)

    def send(self, *, to: str, body: str) -> SmsResult:
        if not self.configured:
            return SmsResult(delivered=False, simulated=False, attempts=0,
                             error="Twilio not configured (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER)")
        if not self._override_to:
            return SmsResult(delivered=False, simulated=False, attempts=0, skipped=True,
                             error="GHOSTSHIFT_DEMO_TECHNICIAN_PHONE not set; real SMS is only sent to an explicitly configured number")
        url = self.API.format(sid=self._sid)
        last_error = None
        with httpx.Client(timeout=10.0, transport=self._transport, auth=(self._sid, self._token)) as client:
            for attempt in range(1, self._max_attempts + 1):
                try:
                    r = client.post(url, data={"To": self._override_to, "From": self._from, "Body": body})
                except httpx.HTTPError as exc:
                    last_error = f"Network error: {exc}"
                else:
                    if r.status_code in (200, 201):
                        return SmsResult(delivered=True, simulated=False, attempts=attempt, external_id=r.json().get("sid"))
                    detail = _twilio_error(r)
                    last_error = f"Twilio HTTP {r.status_code}: {detail}"
                    if r.status_code != 429 and r.status_code < 500:
                        return SmsResult(delivered=False, simulated=False, attempts=attempt, error=last_error)
                if attempt < self._max_attempts:
                    self._sleep(min(4.0, 0.5 * 2 ** (attempt - 1)))
        return SmsResult(delivered=False, simulated=False, attempts=self._max_attempts, error=last_error)

    def health(self) -> ProviderHealth:
        if not self.configured:
            detail = "Missing TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER"
        elif not self._override_to:
            detail = "Configured, but GHOSTSHIFT_DEMO_TECHNICIAN_PHONE is unset so sends will be skipped"
        else:
            detail = "Configured; sends to GHOSTSHIFT_DEMO_TECHNICIAN_PHONE only (not probed)"
        return ProviderHealth(capability="sms", provider=self.info, configured=self.configured, available=None, detail=detail)


def _twilio_error(r: httpx.Response) -> str:
    try:
        j = r.json()
        return f"{j.get('code')}: {j.get('message')}"
    except ValueError:
        return r.text[:200]
