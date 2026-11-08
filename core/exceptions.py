"""Consistent, safe JSON error responses for the whole API.

Every error response has the shape::

    {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}

Unexpected exceptions are logged server-side and returned as a generic 500
response so that stack traces and database details never reach API clients.
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ServiceUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The service is temporarily unavailable."
    default_code = "service_unavailable"


def _first_message(detail) -> str:
    if isinstance(detail, list) and detail:
        return _first_message(detail[0])
    if isinstance(detail, dict) and detail:
        key, value = next(iter(detail.items()))
        message = _first_message(value)
        return message if key in ("non_field_errors", "detail") else f"{key}: {message}"
    return str(detail)


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)

    if response is None:
        view = context.get("view")
        logger.exception("Unhandled error in %s", view.__class__.__name__ if view else "unknown view")
        return Response(
            {
                "success": False,
                "error": {
                    "code": "server_error",
                    "message": "An unexpected error occurred. Please try again later.",
                },
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    if isinstance(exc, exceptions.ValidationError):
        code = "validation_error"
        message = _first_message(detail)
        details = detail
    else:
        codes = exc.get_codes() if isinstance(exc, exceptions.APIException) else None
        code = codes if isinstance(codes, str) else "error"
        message = detail.get("detail", _first_message(detail)) if isinstance(detail, dict) else _first_message(detail)
        details = None

    payload = {"success": False, "error": {"code": code, "message": str(message)}}
    if details is not None:
        payload["error"]["details"] = details
    if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
        payload["error"]["retry_after_seconds"] = int(exc.wait)
    response.data = payload
    return response
