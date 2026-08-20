"""HTTP contracts for durable bot rooms."""

from __future__ import annotations

import asyncio
import json
import inspect

from starlette.responses import JSONResponse
try:
    from starlette.responses import StreamingResponse
except (ImportError, AttributeError):  # Lightweight dashboard test stubs.
    class StreamingResponse:
        def __init__(self, content, media_type=None, headers=None, status_code=200):
            self.body_iterator = content
            self.media_type = media_type
            self.headers = headers or {}
            self.status_code = status_code


MAX_SHARED_BODY = 16 * 1024


async def _json_body(request):
    try:
        if hasattr(request, "stream"):
            chunks = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_SHARED_BODY:
                    raise ValueError(f"Request body may be at most {MAX_SHARED_BODY} bytes")
                chunks.append(chunk)
            body = b"".join(chunks)
        else:
            body = await request.body()
            if len(body) > MAX_SHARED_BODY:
                raise ValueError(f"Request body may be at most {MAX_SHARED_BODY} bytes")
        value = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Invalid JSON body")
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _error(exc):
    return JSONResponse(
        {"error": str(exc)},
        status_code=400 if isinstance(exc, ValueError) else 502,
    )


async def list_bot_rooms_endpoint(request, *, list_rooms):
    try:
        return JSONResponse({"rooms": list_rooms()})
    except Exception as exc:
        return _error(exc)


async def get_bot_room_endpoint(request, *, load_room):
    try:
        return JSONResponse({"room": load_room(request.path_params["room_id"])})
    except Exception as exc:
        return _error(exc)


async def put_bot_room_endpoint(request, *, save_room):
    try:
        data = await _json_body(request)
        unknown = sorted(set(data) - {"conversation", "session_id"})
        if unknown:
            raise ValueError(f"Unsupported fields: {', '.join(unknown)}")
        if "conversation" not in data:
            raise ValueError("conversation is required")
        room = save_room(
            request.path_params["room_id"],
            conversation=data["conversation"],
            session_id=data.get("session_id"),
        )
        return JSONResponse({"room": room})
    except Exception as exc:
        return _error(exc)


async def shared_message_endpoint(request, *, send_message):
    try:
        data = await _json_body(request)
        if set(data) != {"message"}:
            raise ValueError("Expected a JSON object with only a message field")
        result = send_message(data["message"])
        if inspect.isawaitable(result):
            result = await result
        return JSONResponse(result)
    except Exception as exc:
        return _error(exc)


async def shared_message_stream_endpoint(request, *, send_message):
    try:
        data = await _json_body(request)
        if set(data) != {"message"}:
            raise ValueError("Expected a JSON object with only a message field")
    except Exception as exc:
        return _error(exc)

    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def emit(event):
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def run():
        try:
            result = send_message(data["message"], emit)
            if inspect.isawaitable(result):
                result = await result
            await queue.put({
                "type": "complete",
                "room": result.get("room"),
                "conversation": result.get("conversation", []),
                "summary": result.get("summary", {}),
                "errors": result.get("errors", []),
            })
        except Exception as exc:
            await queue.put({"type": "error", "error": str(exc)[:300]})

    task = asyncio.create_task(run())

    async def events():
        try:
            while True:
                event = await queue.get()
                yield json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
                if event.get("type") in {"complete", "error"}:
                    break
        finally:
            await task

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"X-Content-Type-Options": "nosniff"})
