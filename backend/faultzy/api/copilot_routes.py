"""Copilot API (agentic Bedrock layer). Owned by docs/workstreams/1-agentic-copilot.md.

Registered in `faultzy.main`. Add endpoints here; keep them under /api/copilot.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/copilot", tags=["copilot"])
