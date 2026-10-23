"""Amazon Bedrock Converse adapter (boto3).

No client is created until the first call, so importing this module or building
the container never touches the network or requires credentials.

Before choosing a model in a new AWS account, run `make check-bedrock` (see
scripts/check_bedrock.py): many newer models require a cross-region inference
profile id (e.g. `us.<provider>.<model>`) rather than the bare model id, and the
role needs `bedrock:InvokeModel` on both the profile and the underlying model.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..schemas.common import ProviderKind
from .base import LlmResponse, ProviderError, ProviderHealth, ProviderNotConfigured, info

RETRYABLE_CODES = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelTimeoutException",
    "ModelNotReadyException",
}


def _default_client_factory(region: str, timeout_s: float):
    import boto3
    from botocore.config import Config

    cfg = Config(
        region_name=region,
        connect_timeout=5,
        read_timeout=timeout_s,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    return boto3.client("bedrock-runtime", config=cfg)


class BedrockConverseLLM:
    def __init__(
        self,
        *,
        model_id: str | None,
        region: str,
        timeout_s: float = 20.0,
        client_factory: Callable[[str, float], Any] | None = None,
    ):
        self.model_id = model_id
        self.region = region
        self.timeout_s = timeout_s
        self._factory = client_factory or _default_client_factory
        self._client = None
        self.info = info("bedrock-converse", ProviderKind.external, model_id=model_id)

    def _get_client(self):
        if not self.model_id:
            raise ProviderNotConfigured("FAULTZY_BEDROCK_MODEL_ID is not set")
        if self._client is None:
            self._client = self._factory(self.region, self.timeout_s)
        return self._client

    def complete(self, system: str, prompt: str, *, max_tokens: int = 700) -> LlmResponse:
        client = self._get_client()
        started = time.perf_counter()
        try:
            resp = client.converse(
                modelId=self.model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.2},
            )
        except Exception as exc:  # botocore errors are imported lazily
            raise _translate(exc) from exc
        try:
            blocks = resp["output"]["message"]["content"]
            text = "".join(b.get("text", "") for b in blocks)
        except (KeyError, TypeError) as exc:
            raise ProviderError(f"Unexpected Converse response shape: {exc}") from exc
        usage = resp.get("usage", {})
        return LlmResponse(
            text=text,
            model_id=self.model_id,
            latency_ms=(time.perf_counter() - started) * 1000,
            input_tokens=usage.get("inputTokens"),
            output_tokens=usage.get("outputTokens"),
        )

    def health(self, probe: bool = False) -> ProviderHealth:
        if not self.model_id:
            return ProviderHealth(capability="llm", provider=self.info, configured=False, available=False,
                                  detail="Set FAULTZY_BEDROCK_MODEL_ID (verify access with `make check-bedrock`)")
        if not probe:
            return ProviderHealth(capability="llm", provider=self.info, configured=True, available=None,
                                  detail=f"{self.model_id} in {self.region} (not probed; use ?probe=true)")
        try:
            r = self.complete("Reply with the single word OK.", "ping", max_tokens=5)
            return ProviderHealth(capability="llm", provider=self.info, configured=True, available=True,
                                  detail=f"Converse OK in {r.latency_ms:.0f} ms")
        except ProviderError as exc:
            return ProviderHealth(capability="llm", provider=self.info, configured=True, available=False, detail=str(exc))


def _translate(exc: Exception) -> ProviderError:
    name = type(exc).__name__
    if name in {"NoCredentialsError", "PartialCredentialsError", "NoRegionError"}:
        return ProviderNotConfigured(f"AWS credentials/region not available: {exc}")
    if name in {"EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError"}:
        return ProviderError(f"Bedrock unreachable: {exc}", retryable=True)
    code = getattr(exc, "response", {}).get("Error", {}).get("Code") if hasattr(exc, "response") else None
    if code:
        hint = ""
        if code == "ValidationException" and "inference profile" in str(exc).lower():
            hint = " (this model needs an inference profile id, e.g. 'us.' prefix)"
        if code == "AccessDeniedException":
            hint = " (check model access in the Bedrock console and IAM bedrock:InvokeModel)"
        return ProviderError(f"Bedrock {code}: {exc}{hint}", retryable=code in RETRYABLE_CODES)
    return ProviderError(f"Bedrock call failed: {name}: {exc}")
