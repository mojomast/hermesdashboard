"""HTTP contracts for the reversible Kanban deployment control."""

from __future__ import annotations

import inspect
import json

from starlette.responses import JSONResponse


MAX_BODY = 8 * 1024


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


async def _json_body(request):
    if hasattr(request, "stream"):
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BODY:
                raise ValueError("Request body may be at most 8 KiB")
            chunks.append(chunk)
        raw = b"".join(chunks)
    else:
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise ValueError("Request body may be at most 8 KiB")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid JSON body")
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


async def kanban_status_endpoint(request, *, get_status):
    try:
        return JSONResponse(await _resolve(get_status()))
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def kanban_control_endpoint(request, *, set_enabled, authorize):
    try:
        body = await _json_body(request)
        if body.get("intent") != "kanban_deployment_control":
            raise ValueError("Explicit Kanban deployment intent is required")
        action = str(body.get("action") or "").strip().lower()
        if action not in {"enable", "disable"}:
            raise ValueError("action must be enable or disable")
        if not await _resolve(authorize(str(body.get("passphrase") or ""))):
            return JSONResponse({"error": "approval passphrase required"}, status_code=403)
        status = await _resolve(set_enabled(action == "enable"))
        return JSONResponse(status)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
