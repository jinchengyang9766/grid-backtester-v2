"""Standard JSON API error envelope (SPEC Section 26).

Every non-2xx JSON response uses:

    {"error": {"code": "...", "message": "...", "details": {...}}}

with ``details`` omitted entirely when there is nothing structured to add.
"""

from collections.abc import Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

__all__ = ["ApiError", "error_response", "register_error_handlers"]


class ApiError(Exception):
    """Typed application error carrying the standard envelope fields."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, object] | None = None,
) -> JSONResponse:
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = dict(details)
    return JSONResponse(status_code=status_code, content={"error": error})


async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Only locations, messages, and error types — never the raw input values
    # (FastAPI's default 422 body would echo a submitted plaintext password).
    errors = [
        {
            "loc": [str(part) for part in issue["loc"]],
            "message": issue["msg"],
            "type": issue["type"],
        }
        for issue in exc.errors()
    ]
    return error_response(
        422,
        "VALIDATION_ERROR",
        "Request validation failed.",
        {"errors": errors},
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(ApiError, _handle_api_error)
    application.add_exception_handler(RequestValidationError, _handle_validation_error)
