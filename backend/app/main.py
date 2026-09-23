"""FastAPI application factory and process startup lifecycle.

Imports:
    ``asynccontextmanager`` defines startup/shutdown lifecycle scope.
    FastAPI/CORS/JSONResponse build the HTTP application boundary.
    Version, settings, logging, database, and route modules supply the app's
    identity, configuration, startup services, and endpoints.

``create_app`` is the testable factory.  The module-level ``app`` is the ASGI
object used by Uvicorn and other deployment runners.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes_blocks import router as blocks_router
from app.api.routes_health import router as health_router
from app.api.routes_history import router as history_router
from app.api.routes_language import router as language_router
from app.api.routes_language_connection import router as language_connection_router
from app.api.routes_operations import router as operations_router
from app.api.routes_projects import router as projects_router
from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.core.access_logging import protect_access_logs
from app.db import init_db
from app.services.transactions import WriteBusyError
from app.services.job_records import ProjectBusyError, UnresolvedExternalWorkError
from app.workers.operation_dispatcher import mark_interrupted_operation_jobs, run_operation_dispatcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize process-wide services for the ASGI application lifetime.

    Args:
        app: FastAPI instance entering its lifespan.  The argument is required
            by the framework and is not otherwise inspected.

    Side Effects:
        Configures Loguru, loads settings, logs startup identity, and creates
        or updates local database tables, marks interrupted durable jobs, and
        runs the pending-operation dispatcher until shutdown.

    """
    configure_logging()
    protect_access_logs()
    settings = get_settings()
    log.info(
        "starting BlockVideo version={version} env={env}",
        version=__version__,
        env=settings.environment,
    )
    init_db()
    mark_interrupted_operation_jobs()
    dispatcher = asyncio.create_task(run_operation_dispatcher())
    try:
        yield
    finally:
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Returns:
        A new FastAPI instance with permissive local-development CORS, health,
        project, and block routers under ``/api``, plus a final unexpected-error
        handler that returns a short JSON response.

    Side Effects:
        Reads cached settings while constructing middleware configuration; the
        database itself is initialized later by ``lifespan``.

    """
    settings = get_settings()
    app = FastAPI(
        title="BlockVideo API",
        version=__version__,
        lifespan=lifespan,
        # Do not include docs URLs in production-style defaults; keep them for MVP.
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(projects_router, prefix="/api")
    app.include_router(blocks_router, prefix="/api")
    app.include_router(operations_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(language_router, prefix="/api")
    app.include_router(language_connection_router, prefix="/api")

    @app.exception_handler(UnresolvedExternalWorkError)
    async def _external_unknown(_request, exc: UnresolvedExternalWorkError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ProjectBusyError)
    async def _project_busy(_request, exc: ProjectBusyError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(WriteBusyError)
    async def _write_busy(_request, exc: WriteBusyError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)},
                            headers={"Retry-After": "1"})

    @app.exception_handler(Exception)
    async def _unhandled(_request, exc: Exception) -> JSONResponse:
        """Convert an unexpected exception into a fixed, correlatable response."""
        correlation_id = uuid.uuid4().hex[:16]
        route = _request.scope.get("route")
        path = getattr(route, "path", "unknown")
        log.error(
            "unhandled exception correlation_id={correlation_id} path={path} error_class={error_class}",
            correlation_id=correlation_id,
            path=path,
            error_class=exc.__class__.__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "reason_code": "internal_error",
                    "message": "処理に失敗しました。再読み込み後も続く場合は記録番号を確認してください。",
                    "correlation_id": correlation_id,
                },
            },
        )

    return app


# ASGI entry point imported by Uvicorn/Gunicorn-style runners.
app = create_app()
