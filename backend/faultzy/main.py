"""FastAPI application factory.

    uv run uvicorn faultzy.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import APP_NAME, __version__
from .api import autonomy_routes, copilot_routes
from .api.routes import router
from .api.static import mount_frontend
from .approvals import GateError
from .container import Container, build_container


def _error(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "details": details}})


def create_app(container: Container | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    container = container or build_container()
    app = FastAPI(title=f"{APP_NAME} API", version=__version__,
                  description="Faultzy predictive maintenance and maintenance-coordination API")
    app.state.container = container
    app.add_middleware(CORSMiddleware, allow_origins=container.settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT"], allow_headers=["Content-Type"])
    app.include_router(router)
    app.include_router(copilot_routes.router)
    app.include_router(autonomy_routes.router)

    @app.exception_handler(GateError)
    async def _gate(_: Request, exc: GateError):
        return _error(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 409: "conflict", 403: "forbidden"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        return _error(422, "validation_error", "Request failed validation", {"errors": exc.errors()})

    # Must come after the API routers: it adds a catch-all route.
    if not mount_frontend(app, container.settings.static_dir):

        @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
        def root():
            return {"app": APP_NAME, "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
