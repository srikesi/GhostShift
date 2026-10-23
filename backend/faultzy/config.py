"""Validated runtime configuration.

All settings come from environment variables (optionally a `.env` file at the
repository root or in `backend/`). Nothing here performs network I/O, so the
application always starts without credentials.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
REPO_DIR = BACKEND_DIR.parent


class ExecutionMode(str, Enum):
    """How Faultzy chooses between real integrations and deterministic stubs.

    demo  -- never call external services; every provider is a deterministic stub.
    aws   -- use configured real integrations; failures are reported, never masked.
    auto  -- try configured real integrations; on documented failure conditions
             (missing config, provider error, invalid output) fall back to the
             deterministic path and label the result `deterministic_fallback`.
    """

    demo = "demo"
    aws = "aws"
    auto = "auto"


class SmsProviderChoice(str, Enum):
    stub = "stub"
    twilio = "twilio"


class VoiceProviderChoice(str, Enum):
    stub = "stub"
    elevenlabs = "elevenlabs"


class LlmProviderChoice(str, Enum):
    template = "template"
    bedrock = "bedrock"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FAULTZY_",
        env_file=(str(REPO_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: ExecutionMode = ExecutionMode.demo
    data_dir: Path = PACKAGE_DIR / "fixtures"
    # Optional real dataset: path to ai4i2020.csv registers machine AI4I-MILL.
    ai4i_path: Path | None = None
    # --- Workstream 3 (data & organizer requirements): add data/AWS-source settings below ---

    # Serve the built frontend (frontend/dist) from the API, for single-container deploys.
    static_dir: Path | None = None
    # --- Workstream 2 (deploy & live messaging): add deployment settings below ---

    public_base_url: str = "http://localhost:5173"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- LLM (Amazon Bedrock Converse) ---------------------------------------
    llm_provider: LlmProviderChoice = LlmProviderChoice.bedrock
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("FAULTZY_AWS_REGION", "AWS_REGION", "AWS_DEFAULT_REGION"),
    )
    # Deliberately no default: verify model access / inference profile in the
    # workshop account first (see `make check-bedrock`).
    bedrock_model_id: str | None = None
    llm_timeout_s: float = 20.0
    llm_max_attempts: int = Field(default=2, ge=1, le=5)
    # --- Workstream 1 (agentic copilot): add copilot/agent settings below ---
    # advise: people approve every order. autopilot: Faultzy places parts orders itself within the limit.
    autonomy_level: str = Field(default="advise", pattern="^(advise|autopilot)$")
    auto_order_limit_usd: float = Field(default=2500.0, ge=0)


    # --- Twilio SMS ------------------------------------------------------------
    sms_provider: SmsProviderChoice = SmsProviderChoice.stub
    twilio_account_sid: str | None = Field(default=None, validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: SecretStr | None = Field(default=None, validation_alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str | None = Field(default=None, validation_alias="TWILIO_FROM_NUMBER")
    sms_max_attempts: int = Field(default=3, ge=1, le=5)
    # Real SMS is only sent to this number (opt-in, e.g. your own phone).
    demo_technician_phone: str | None = None

    # --- ElevenLabs voice --------------------------------------------------------
    voice_provider: VoiceProviderChoice = VoiceProviderChoice.stub
    elevenlabs_api_key: SecretStr | None = Field(default=None, validation_alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str | None = Field(default=None, validation_alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = "eleven_multilingual_v2"

    # --- Workflow --------------------------------------------------------------
    stage_timeout_s: float = 30.0
    inspection_token_ttl_hours: float = 12.0

    @field_validator("public_base_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number)

    @property
    def elevenlabs_configured(self) -> bool:
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    @property
    def bedrock_configured(self) -> bool:
        return bool(self.bedrock_model_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
