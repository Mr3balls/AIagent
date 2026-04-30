import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import Base, engine
from app.routers.analyze_router import router as analyze_router
from app.routers.auth import router as auth_router
from app.routers.tenders import router as tenders_router
from app.routers.upload_router import router as upload_router

logger = logging.getLogger(__name__)
settings = get_settings()


def _startup_checks() -> None:
    errors: list[str] = []

    if not settings.openai_api_key:
        msg = "OPENAI_API_KEY is not set"
        logger.error(msg)
        errors.append(msg)

    weak_keys = {"", "change_me_super_secret_key"}
    if settings.jwt_secret_key in weak_keys:
        msg = (
            "JWT_SECRET_KEY is not set or uses the default insecure value. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
        logger.error(msg)
        errors.append(msg)

    if errors and not settings.debug:
        raise RuntimeError(
            "Startup checks failed. Set DEBUG=true to bypass in development. Errors: "
            + "; ".join(errors)
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _startup_checks()
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(tenders_router, prefix=settings.api_prefix)
app.include_router(upload_router, prefix=settings.api_prefix)
app.include_router(analyze_router, prefix=settings.api_prefix)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "version": settings.app_version,
        "model": settings.openai_model,
    }
