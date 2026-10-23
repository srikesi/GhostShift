"""Voice briefing: text-only stub and ElevenLabs text-to-speech adapter.

Voice is an optional enhancement. Diagnosis, notification and approval never
depend on it; the briefing text is always returned even if audio fails.
"""

from __future__ import annotations

import httpx

from ..schemas.common import ProviderKind
from .base import ProviderHealth, VoiceResult, info


class TextOnlyVoice:
    info = info("voice-text-only", ProviderKind.stub)

    def synthesize(self, text: str) -> VoiceResult:
        return VoiceResult(audio=None, mime_type=None, simulated=True)

    def health(self) -> ProviderHealth:
        return ProviderHealth(capability="voice", provider=self.info, configured=True, available=True,
                              detail="Text-only briefing (no audio generated)")


class ElevenLabsVoice:
    API = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    def __init__(self, *, api_key: str | None, voice_id: str | None, model_id: str,
                 transport: httpx.BaseTransport | None = None):
        self._key = api_key
        self._voice = voice_id
        self._model = model_id
        self._transport = transport
        self.info = info("elevenlabs", ProviderKind.external, model_id=model_id)

    def synthesize(self, text: str) -> VoiceResult:
        if not (self._key and self._voice):
            return VoiceResult(audio=None, mime_type=None, simulated=False,
                               error="ElevenLabs not configured (ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID)")
        try:
            with httpx.Client(timeout=20.0, transport=self._transport) as client:
                r = client.post(
                    self.API.format(voice_id=self._voice),
                    headers={"xi-api-key": self._key, "accept": "audio/mpeg"},
                    json={"text": text, "model_id": self._model},
                )
        except httpx.HTTPError as exc:
            return VoiceResult(audio=None, mime_type=None, simulated=False, error=f"Network error: {exc}")
        if r.status_code != 200:
            return VoiceResult(audio=None, mime_type=None, simulated=False,
                               error=f"ElevenLabs HTTP {r.status_code}: {r.text[:200]}")
        return VoiceResult(audio=r.content, mime_type="audio/mpeg", simulated=False)

    def health(self) -> ProviderHealth:
        ok = bool(self._key and self._voice)
        return ProviderHealth(capability="voice", provider=self.info, configured=ok, available=None,
                              detail="Configured (not probed)" if ok else "Missing ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID")
