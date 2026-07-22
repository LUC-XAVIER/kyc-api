"""Domain exceptions and FastAPI exception handlers.

Centralizes error responses so the API returns consistent, descriptive
JSON payloads (e.g. the 400 / quota-exceeded flows in Analysis doc UC1).
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.errors")


class KycError(Exception):
    """Base class for domain errors raised by the KYC-API backend."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "KYC_ERROR"

    def __init__(self, message: str) -> None:
        """Initialize with a human-readable message."""
        self.message = message
        super().__init__(message)


class QuotaExceededError(KycError):
    """Raised when an MFI has reached its monthly verification quota."""

    status_code = status.HTTP_402_PAYMENT_REQUIRED
    code = "QUOTA_EXCEEDED"


class AuthenticationError(KycError):
    """Raised when API-key or token authentication fails."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "AUTHENTICATION_FAILED"


class AuthorizationError(KycError):
    """Raised when an authenticated caller lacks the required role."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "AUTHORIZATION_FAILED"


class ValidationError(KycError):
    """Raised when an inbound verification request is malformed."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "VALIDATION_FAILED"


class NotFoundError(KycError):
    """Raised when a requested resource does not exist for the caller."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


class ConflictError(KycError):
    """Raised when a request collides with existing state.

    For example, a client ID already used by this MFI.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


class EmailError(KycError):
    """Raised when an outbound email could not be sent (SMTP failure)."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "EMAIL_FAILED"


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that render :class:`KycError` as JSON responses."""

    @app.exception_handler(KycError)
    async def _handle_kyc_error(  # type: ignore[unused-ignore]
        _: Request, exc: KycError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(  # type: ignore[unused-ignore]
        request: Request, exc: Exception
    ) -> JSONResponse:
        # Handling the exception here (rather than letting it 500 unhandled)
        # keeps the response inside the middleware stack, so CORS headers are
        # still applied and the browser sees the real error, not a CORS one.
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                }
            },
        )
