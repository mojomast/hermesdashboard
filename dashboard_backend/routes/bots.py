"""HTTP contracts for profile-backed bots."""

from __future__ import annotations

import json
import inspect

from starlette.responses import JSONResponse
try:
    from starlette.responses import FileResponse
except (ImportError, AttributeError):  # Lightweight dashboard test stubs.
    class _Headers(dict):
        def __setitem__(self, key, value):
            super().__setitem__(str(key).lower(), value)

        def __getitem__(self, key):
            return super().__getitem__(str(key).lower())

    class FileResponse:
        def __init__(self, path, media_type=None, filename=None, **kwargs):
            self.path = path
            self.media_type = media_type
            self.filename = filename
            self.headers = _Headers()
            self.status_code = 200


MAX_JSON_BODY = 64 * 1024
MAX_AVATAR_BODY = 2 * 1024 * 1024
AVATAR_CONTENT_TYPES = {"image/png", "image/jpeg", "image/webp"}


async def _json_body(request):
    try:
        value = json.loads(await _bounded_body(request, MAX_JSON_BODY))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid JSON body")
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


async def _bounded_body(request, maximum):
    if not hasattr(request, "stream"):
        body = await request.body()
        if len(body) > maximum:
            raise ValueError(f"Request body may be at most {maximum} bytes")
        return body
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum:
            raise ValueError(f"Request body may be at most {maximum} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _error(exc):
    if isinstance(exc, FileNotFoundError):
        status = 404
    elif isinstance(exc, (ValueError, FileExistsError)):
        status = 400 if isinstance(exc, ValueError) else 409
    elif isinstance(exc, ImportError):
        status = 503
    else:
        status = 500
    return JSONResponse({"error": str(exc)}, status_code=status)


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


async def list_bots_endpoint(request, *, list_bots):
    try:
        return JSONResponse({"bots": await _resolve(list_bots())})
    except Exception as exc:
        return _error(exc)


async def get_bot_endpoint(request, *, get_bot):
    try:
        return JSONResponse({"bot": await _resolve(get_bot(request.path_params["name"]))})
    except Exception as exc:
        return _error(exc)


async def put_avatar_endpoint(request, *, save_avatar):
    try:
        content_type = str(request.headers.get("content-type", "")).split(";", 1)[0].strip().lower()
        if content_type not in AVATAR_CONTENT_TYPES:
            return JSONResponse(
                {"error": "Avatar Content-Type must be image/png, image/jpeg, or image/webp"},
                status_code=415,
            )
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_AVATAR_BODY:
                    return JSONResponse({"error": "Avatar image may be at most 2 MiB"}, status_code=413)
            except ValueError:
                raise ValueError("Invalid Content-Length")
        raw = await _bounded_body(request, MAX_AVATAR_BODY)
        bot = await _resolve(save_avatar(request.path_params["name"], raw, content_type))
        return JSONResponse({"bot": bot})
    except Exception as exc:
        return _error(exc)


async def get_avatar_endpoint(request, *, get_avatar):
    try:
        path, digest = await _resolve(get_avatar(request.path_params["name"]))
        response = FileResponse(path, media_type="image/png", filename=None)
        response.headers["Cache-Control"] = "private, max-age=31536000, immutable"
        response.headers["ETag"] = f'"{digest}"'
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception as exc:
        return _error(exc)


async def delete_avatar_endpoint(request, *, delete_avatar):
    try:
        bot = await _resolve(delete_avatar(request.path_params["name"]))
        return JSONResponse({"bot": bot, "deleted": True})
    except Exception as exc:
        return _error(exc)


async def create_bot_endpoint(request, *, create_bot):
    try:
        result = await _resolve(create_bot(await _json_body(request)))
        return JSONResponse(result, status_code=201)
    except Exception as exc:
        return _error(exc)


async def update_bot_endpoint(request, *, update_bot):
    try:
        bot = await _resolve(update_bot(request.path_params["name"], await _json_body(request)))
        return JSONResponse({"bot": bot})
    except Exception as exc:
        return _error(exc)


async def delete_bot_endpoint(request, *, hide_bot):
    try:
        bot = await _resolve(hide_bot(request.path_params["name"]))
        return JSONResponse({"bot": bot, "hidden": True})
    except Exception as exc:
        return _error(exc)
