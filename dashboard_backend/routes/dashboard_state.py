"""Dashboard state HTTP request wrappers.

This module owns only route-wrapper behavior: request parsing, JSON response
envelopes, and HTTP status mapping for the dashboard-state API routes. The
state persistence service and app-level compatibility seams are injected by
``app.py`` at call time.
"""

from __future__ import annotations

import json

from starlette.responses import JSONResponse


async def get_dashboard_state_endpoint(request, *, load_state):
    """Return the persisted dashboard state projection for a supported key."""
    key = request.path_params["key"]
    try:
        found, value = load_state(key)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"found": found, "value": value})


async def set_dashboard_state_endpoint(request, *, save_state):
    """Persist a dashboard state projection value from a JSON request body."""
    key = request.path_params["key"]
    try:
        data = json.loads(await request.body())
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    if not isinstance(data, dict) or "value" not in data:
        return JSONResponse({"error": "Expected JSON object with a value field"}, status_code=400)
    try:
        save_state(key, data.get("value"))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"success": True})


async def delete_dashboard_state_endpoint(request, *, delete_state):
    """Delete a persisted dashboard state projection value for a supported key."""
    key = request.path_params["key"]
    try:
        delete_state(key)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"success": True})
