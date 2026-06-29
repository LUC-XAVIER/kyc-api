"""FastAPI application factory for the KYC-API backend.

Wires configuration, logging, CORS, exception handlers, and the v1 API
router. Auto-generated Swagger docs are served at ``/docs`` (NFR07).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Automated biometric identity verification platform for "
            "Microfinance Institutions in Cameroon."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    logger.info(
        "%s application initialized (%s)",
        settings.app_name,
        settings.environment,
    )
    return app


app = create_app()
