"""Optionally serve the built frontend from the API process (single-container deploys).

Set GHOSTSHIFT_STATIC_DIR to the Vite build output (frontend/dist). API routes keep
priority; any other path returns the file if it exists, else index.html so
client-side routes such as /m/<token> work.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse


def mount_frontend(app: FastAPI, static_dir: Path | None) -> bool:
    if not static_dir or not (static_dir / "index.html").exists():
        return False
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(root / "index.html")

    return True
