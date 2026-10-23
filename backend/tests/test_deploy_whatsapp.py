"""Twilio WhatsApp sandbox: a whatsapp: sender sends to a whatsapp: recipient."""

from __future__ import annotations

import httpx

from ghostshift.integrations.sms import TwilioSms


def _client(from_number, seen):
    def handler(req: httpx.Request):
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"sid": "SM1"})

    return TwilioSms(account_sid="AC1", auth_token="t", from_number=from_number, override_to="+15125550100",
                     transport=httpx.MockTransport(handler), sleep=lambda _: None)


def test_whatsapp_sender_prefixes_recipient():
    seen = {}
    assert _client("whatsapp:+14155238886", seen).send(to="ignored", body="b").delivered
    assert "To=whatsapp%3A%2B15125550100" in seen["body"] and "From=whatsapp%3A%2B14155238886" in seen["body"]


def test_sms_sender_keeps_plain_recipient():
    seen = {}
    _client("+15125550000", seen).send(to="ignored", body="b")
    assert "To=%2B15125550100" in seen["body"]
