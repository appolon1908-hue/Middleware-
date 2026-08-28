"""Streaming request-body limits applied before application parsing."""

from __future__ import annotations

from fastapi import Request

from .problems import ProblemError


def _declared_length(request: Request) -> int | None:
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw, 10)
    except ValueError as error:
        raise ProblemError(
            status=400,
            code="REQUEST_CONTENT_LENGTH_INVALID",
            title="Invalid Content-Length",
            detail="Content-Length must be a non-negative decimal integer.",
        ) from error
    if value < 0:
        raise ProblemError(
            status=400,
            code="REQUEST_CONTENT_LENGTH_INVALID",
            title="Invalid Content-Length",
            detail="Content-Length must be a non-negative decimal integer.",
        )
    return value


async def read_bounded_body(
    request: Request,
    *,
    maximum_bytes: int,
    too_large_code: str,
    title: str,
    detail: str,
) -> bytes:
    """Read at most ``maximum_bytes`` and cache the bounded body for FastAPI."""

    declared = _declared_length(request)
    if declared is not None and declared > maximum_bytes:
        raise ProblemError(
            status=413,
            code=too_large_code,
            title=title,
            detail=detail,
        )

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > maximum_bytes:
            raise ProblemError(
                status=413,
                code=too_large_code,
                title=title,
                detail=detail,
            )
        body.extend(chunk)

    bounded = bytes(body)
    # Starlette's Request.body() uses the same cache. Setting it here lets the
    # downstream FastAPI parser consume the already bounded bytes.
    request._body = bounded
    return bounded


__all__ = ["read_bounded_body"]
