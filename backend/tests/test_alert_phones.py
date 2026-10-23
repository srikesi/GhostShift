import httpx

from ghostshift.config import Settings
from ghostshift.container import choose_sms
from ghostshift.integrations.sms import MultiSms, TwilioSms


def test_extra_alert_phones_parse_and_skip_the_primary():
    s = Settings(_env_file=None, demo_technician_phone="+15125550100", alert_phones=" +15125550101, +15125550100 ,+15125550102 ")
    assert s.extra_alert_phones == ["+15125550101", "+15125550102"]


def test_every_number_gets_the_alert_and_one_failure_does_not_block_the_rest():
    sent = []

    def handler(req: httpx.Request):
        to = dict(x.split("=") for x in req.content.decode().split("&"))["To"]
        sent.append(to)
        return httpx.Response(400, json={"code": 21211, "message": "bad number"}) if to.endswith("101") else httpx.Response(201, json={"sid": "SM1"})

    def tw(to):
        return TwilioSms(account_sid="AC1", auth_token="t", from_number="+15125550000", override_to=to, max_attempts=1,
                         transport=httpx.MockTransport(handler))

    multi = MultiSms([tw("+15125550100"), tw("+15125550101"), tw("+15125550102")])
    r = multi.send(to="x", body="hi")
    assert r.delivered and r.external_id == "SM1"
    assert sorted(t.replace("%2B", "+") for t in sent) == ["+15125550100", "+15125550101", "+15125550102"]


def test_primary_failure_still_counts_as_sent_if_another_number_got_it():
    def tw(to, ok):
        return TwilioSms(account_sid="AC1", auth_token="t", from_number="+15125550000", override_to=to, max_attempts=1,
                         transport=httpx.MockTransport(lambda r: httpx.Response(201, json={"sid": "SM2"}) if ok else httpx.Response(400, json={})))
    assert MultiSms([tw("+1", False), tw("+2", True)]).send(to="x", body="b").delivered


def test_choose_sms_fans_out_only_when_extra_numbers_are_set():
    base = dict(_env_file=None, mode="auto", sms_provider="twilio", twilio_account_sid="AC1", twilio_auth_token="t",
                twilio_from_number="+15125550000", demo_technician_phone="+15125550100")
    assert isinstance(choose_sms(Settings(**base)), TwilioSms)
    assert isinstance(choose_sms(Settings(**base, alert_phones="+15125550101")), MultiSms)
