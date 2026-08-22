"""HTTP contract for optional execution-tool descriptions."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse

from dashboard_backend.services.tool_intent import ToolIntentBusy


MAX_BODY_BYTES = 256 * 1024
NO_STORE_HEADERS = {"Cache-Control": "no-store"}


class BodyTooLarge(ValueError):
    pass


def _header(request, name: str) -> str:
    headers = getattr(request, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        return str(headers.get(name, ""))
    return ""


def _same_origin(request) -> bool:
    origin = _header(request, "origin").rstrip("/")
    host = _header(request, "host").lower()
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != host:
        return False
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    forwarded = _header(request, "x-forwarded-proto").split(",", 1)[0].strip()
    expected_scheme = forwarded or getattr(getattr(request, "url", None), "scheme", "")
    return not expected_scheme or parsed.scheme == expected_scheme


async def _read_json(request) -> dict:
    content_length = _header(request, "content-length")
    if content_length:
        try:
            body_length = int(content_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if body_length > MAX_BODY_BYTES:
            raise BodyTooLarge("Request body is too large")

    if hasattr(request, "stream"):
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise BodyTooLarge("Request body is too large")
            chunks.append(chunk)
        raw = b"".join(chunks)
    else:
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            raise BodyTooLarge("Request body is too large")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Expected a JSON object")
    return payload


async def tool_intent_endpoint(request, *, describe):
    if not _same_origin(request):
        return PlainTextResponse("", status_code=403, headers=NO_STORE_HEADERS)
    if _header(request, "content-type").split(";", 1)[0].strip().lower() != "application/json":
        return PlainTextResponse("", status_code=415, headers=NO_STORE_HEADERS)
    try:
        payload = await _read_json(request)
        tool = str(payload.get("tool") or "").strip()
        if tool not in {"terminal", "execute_code"}:
            raise ValueError("Unsupported tool")
        description = await describe(tool, payload.get("arguments"))
    except BodyTooLarge:
        return PlainTextResponse("", status_code=413, headers=NO_STORE_HEADERS)
    except ValueError:
        return PlainTextResponse("", status_code=400, headers=NO_STORE_HEADERS)
    except ToolIntentBusy:
        return PlainTextResponse("", status_code=204, headers=NO_STORE_HEADERS)
    except Exception:
        return PlainTextResponse("", status_code=204, headers=NO_STORE_HEADERS)
    if not description:
        return PlainTextResponse("", status_code=204, headers=NO_STORE_HEADERS)
    return PlainTextResponse(description, headers=NO_STORE_HEADERS)
