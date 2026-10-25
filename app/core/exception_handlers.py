import traceback
from fastapi import Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.exceptions import (
    AppException, ValidationError
)
from app.core.logging import get_logger

logger = get_logger("exception_handlers")


def http_exception_handler(
        request: Request, exc: HTTPException  
    ) -> JSONResponse:

    """
    Args:
        request : Fastapi request
        exc: Fastapi http exception
    
    Returns:
        JSON response in DRF format {"detail" : "error message"}
    """

    logger.warning(
        f"HTTP Error: {exc.detail}",
        extra={
           "status_code" : exc.status_code,
            "path": request.url.path,
            "method": request.method
        },
        stacklevel=2
    )

    return JSONResponse(
        status_code= exc.status_code,
        content={"detail" : exc.detail},
        headers=exc.headers
    )

def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
    """
    Args:
        request: FastAPI request
        exc: Application exception

    Returns:
        JSON response in DRF format {"detail" : "error message"}
    """

    logger.warning(
        f"Application Error: {exc.detail}",
        extra={
            "status_code" : exc.status_code,
            "path": request.url.path,
            "method": request.method
        },
        stacklevel=2
    )
    
    return JSONResponse(
        status_code= exc.status_code,
        content={"detail" : exc.message or exc.detail}
    )

def _serialize_value(value: Any) -> Any:
    """Recursively serialize a value, converting Decimal to string.

    Args:
        value: Value to serialize

    Returns:
        Serialized value
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    return value


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors using Django REST Framework format.

    Args:
        request: FastAPI request object
        exc: Validation error instance

    Returns:
        JSON error response in DRF format: {"field_name": ["error message", ...]}
    """
    errors = exc.errors()

    # Group errors by field name (DRF format)
    # Format: {"field_name": ["error message 1", "error message 2"], ...}
    error_dict: dict[str, list[str]] = {}
    for error in errors:
        # Build field path (e.g., "body.user", "query.page", "path.id")
        field_parts = [str(loc) for loc in error["loc"]]
        field_name = ".".join(field_parts) if field_parts else "non_field_errors"

        # Remove "body" prefix for cleaner field names (DRF style)
        field_name = field_name.removeprefix("body.")  # Remove "body." prefix

        message = error["msg"]

        # Group multiple errors for the same field
        if field_name not in error_dict:
            error_dict[field_name] = []
        error_dict[field_name].append(message)

    # Return DRF format: {"field_name": ["error message", ...]}
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_dict,
    )


async def pydantic_validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """Handle Pydantic model validation errors using Django REST Framework format.

    Args:
        request: FastAPI request object
        exc: Pydantic validation error instance

    Returns:
        JSON error response in DRF format: {"field_name": ["error message", ...]}
    """
    errors = exc.errors()

    # Group errors by field name (DRF format)
    # Format: {"field_name": ["error message 1", "error message 2"], ...}
    error_dict: dict[str, list[str]] = {}
    for error in errors:
        # Build field path (e.g., "body.user", "query.page", "path.id")
        field_parts = [str(loc) for loc in error["loc"]]
        field_name = ".".join(field_parts) if field_parts else "non_field_errors"

        # Remove "body" prefix for cleaner field names (DRF style)
        field_name = field_name.removeprefix("body.")  # Remove "body." prefix

        message = error["msg"]

        # Group multiple errors for the same field
        if field_name not in error_dict:
            error_dict[field_name] = []
        error_dict[field_name].append(message)

    logger.warning(
        "Pydantic validation error",
        extra={
            "path": request.url.path,
            "method": request.method,
            "errors": errors,
        },
        stacklevel=2,
    )

    # Return DRF format: {"field_name": ["error message", ...]}
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_dict,
    )


async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle ValueError exceptions using Django REST Framework format.

    Args:
        request: FastAPI request object
        exc: ValueError instance

    Returns:
        JSON error response in DRF format: {"detail": "error message"}
    """
    logger.warning(
        f"Value error: {exc!s}",
        extra={
            "path": request.url.path,
            "method": request.method,
        },
        stacklevel=2,
    )

    # Return DRF format: {"detail": "error message"}
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions using Django REST Framework format.

    Args:
        request: FastAPI request object
        exc: Exception instance

    Returns:
        JSON error response in DRF format: {"detail": "error message"}
    """
    error_traceback = traceback.format_exc()

    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {exc!s}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "traceback": error_traceback,
        },
        exc_info=True,
        stacklevel=2,
    )

    # In production, don't expose internal error details
    detail = str(exc)
    if not request.app.debug:
        detail = "Internal server error"

    # Return DRF format: {"detail": "error message"}
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": detail},
    )