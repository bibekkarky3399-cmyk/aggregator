from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        code: str = "app_error",
        details: Any = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found", details: Any = None) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            details=details,
        )


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Unauthorized", details: Any = None) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            details=details,
        )


class ConflictError(AppError):
    def __init__(self, message: str = "Conflict", details: Any = None) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_409_CONFLICT,
            code="conflict",
            details=details,
        )


class ProviderError(AppError):
    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="provider_error",
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred",
                    "details": str(exc) if app.debug else None,
                }
            },
        )
