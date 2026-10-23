"""Scheduler calls: start one, and the webhooks Twilio uses to run the conversation."""

from __future__ import annotations

from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..approvals import GateError
from ..calendar_service import ScheduleError
from ..schemas.common import Contract
from ..voice_calls import CallRecord, mask, twilio_signature
from .routes import get_container

router = APIRouter(prefix="/api", tags=["calls"])


class StartCall(Contract):
    incident_id: str


class SayRequest(Contract):
    text: str


class CallView(Contract):
    id: str
    incident_id: str
    to_masked: str
    simulated: bool
    status: str
    outcome: str | None
    confirmed: bool
    accepted_text: str | None
    options: list[str]
    transcript: list[dict[str, str]]
    error: str | None


def _view(c: CallRecord) -> CallView:
    return CallView(id=c.id, incident_id=c.incident_id, to_masked=mask(c.to), simulated=c.simulated, status=c.status,
                    outcome=c.outcome, confirmed=c.confirmed, accepted_text=c.accepted.say() if c.accepted else None,
                    options=[o.say() for o in c.options], transcript=[{"who": w, "text": t} for w, t in c.transcript],
                    error=c.error)


@router.post("/calendar/call", response_model=CallView, status_code=201)
def start_call(body: StartCall, c=Depends(get_container)):
    try:
        return _view(c.calls.start(body.incident_id))
    except ScheduleError as exc:
        raise GateError(exc.status_code, exc.code, exc.message, exc.details) from exc


@router.get("/calendar/calls", response_model=list[CallView])
def list_calls(incident_id: str | None = None, c=Depends(get_container)):
    return [_view(x) for x in c.calls.calls(incident_id)]


@router.post("/voice/calls/{call_id}/say", response_model=CallView)
def say(call_id: str, body: SayRequest, c=Depends(get_container)):
    """Type what the person says. Only for simulated calls (a real call is spoken on the phone)."""
    call = c.calls.get(call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    if not call.simulated:
        raise GateError(409, "not_simulated", "This is a real call. The person answers by phone.")
    if call.status != "completed":
        c.calls.respond(call, body.text)
    return _view(call)


# ---------------------------------------------------------------- Twilio webhooks
async def _twilio(request: Request, c, call_id: str, path: str):
    """Read a Twilio form post and check its signature, so only Twilio can drive a call."""
    call = c.calls.get(call_id)
    if call is None:
        raise HTTPException(404, "Call not found")
    params = dict(parse_qsl((await request.body()).decode(), keep_blank_values=True))
    token = c.settings.twilio_auth_token.get_secret_value() if c.settings.twilio_auth_token else None
    if call.simulated or not token:
        raise HTTPException(403, "Not a live call")
    url = f"{c.settings.public_base_url.rstrip('/')}/api/voice/calls/{call_id}/{path}"
    if twilio_signature(token, url, params) != request.headers.get("X-Twilio-Signature", ""):
        raise HTTPException(403, "Bad signature")
    return call, params


def _xml(body: str) -> Response:
    return Response(body, media_type="application/xml")


@router.post("/voice/calls/{call_id}/twiml")
async def twiml(call_id: str, request: Request, c=Depends(get_container)):
    call, _ = await _twilio(request, c, call_id, "twiml")
    call.status = "in_progress"
    text = c.calls.opening(call)
    if not call.transcript:
        call.transcript.append(("agent", text))
    return _xml(c.calls.gather(f"{c.settings.public_base_url.rstrip('/')}/api/voice/calls/{call_id}/turn", text))


@router.post("/voice/calls/{call_id}/turn")
async def turn(call_id: str, request: Request, c=Depends(get_container)):
    call, params = await _twilio(request, c, call_id, "turn")
    reply, done = c.calls.respond(call, params.get("SpeechResult", ""))
    if done:
        return _xml(c.calls.hangup(reply))
    return _xml(c.calls.gather(f"{c.settings.public_base_url.rstrip('/')}/api/voice/calls/{call_id}/turn", reply))


@router.post("/voice/calls/{call_id}/status")
async def status(call_id: str, request: Request, c=Depends(get_container)):
    call, params = await _twilio(request, c, call_id, "status")
    c.calls.mark_status(call, params.get("CallStatus", ""))
    return Response(status_code=204)
