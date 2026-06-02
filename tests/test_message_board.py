import json
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest import mock


def _install_framework_stubs() -> None:
    if "starlette.applications" not in sys.modules:
        starlette = types.ModuleType("starlette")
        applications = types.ModuleType("starlette.applications")
        routing = types.ModuleType("starlette.routing")
        templating = types.ModuleType("starlette.templating")
        responses = types.ModuleType("starlette.responses")

        class Starlette:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class Route:
            def __init__(self, path, endpoint, **kwargs):
                self.path = path
                self.endpoint = endpoint
                self.kwargs = kwargs

        class Jinja2Templates:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

            def TemplateResponse(self, *args, **kwargs):
                return None

        class _Response:
            def __init__(self, content=None, status_code=200):
                self.status_code = status_code
                if isinstance(content, (dict, list)):
                    self.body = json.dumps(content).encode("utf-8")
                elif isinstance(content, bytes):
                    self.body = content
                else:
                    self.body = str(content or "").encode("utf-8")

        class JSONResponse(_Response):
            pass

        class PlainTextResponse(_Response):
            pass

        applications.Starlette = Starlette
        routing.Route = Route
        templating.Jinja2Templates = Jinja2Templates
        responses.JSONResponse = JSONResponse
        responses.PlainTextResponse = PlainTextResponse

        sys.modules["starlette"] = starlette
        sys.modules["starlette.applications"] = applications
        sys.modules["starlette.routing"] = routing
        sys.modules["starlette.templating"] = templating
        sys.modules["starlette.responses"] = responses

    if "sse_starlette.sse" not in sys.modules:
        sse_starlette = types.ModuleType("sse_starlette")
        sse_module = types.ModuleType("sse_starlette.sse")

        class EventSourceResponse:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        sse_module.EventSourceResponse = EventSourceResponse
        sys.modules["sse_starlette"] = sse_starlette
        sys.modules["sse_starlette.sse"] = sse_module


_install_framework_stubs()

import app as dashboard_app
from tests.dashboard_sources import dashboard_source


class FakeRequest:
    def __init__(self, payload=None):
        self._payload = payload or {}

    async def json(self):
        return self._payload

    async def body(self):
        return json.dumps(self._payload).encode("utf-8")


def _decode(response):
    return json.loads(response.body.decode("utf-8"))


def test_message_board_schema_persists_threads_and_replies(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    post = dashboard_app.create_message_board_post(
        title="Build iteration loop",
        body="Please wire up a dashboard forum so Hermes can reply.",
        author="mojo",
        agent_reply="On it — I will make a persistent board.",
    )

    assert post["id"]
    assert post["title"] == "Build iteration loop"
    assert post["author"] == "mojo"
    assert post["status"] == "answered"
    assert len(post["messages"]) == 2
    assert post["messages"][0]["role"] == "user"
    assert post["messages"][1]["role"] == "assistant"

    posts = dashboard_app.list_message_board_posts()
    assert [item["id"] for item in posts] == [post["id"]]
    assert posts[0]["reply_count"] == 1
    assert posts[0]["last_reply_preview"] == "On it — I will make a persistent board."

    loaded = dashboard_app.get_message_board_post(post["id"])
    assert loaded["messages"][0]["content"].startswith("Please wire")


def test_message_board_validates_empty_posts(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    try:
        dashboard_app.create_message_board_post(title="", body="", author="mojo")
    except ValueError as exc:
        assert "title" in str(exc).lower()
    else:
        raise AssertionError("empty post should be rejected")


def test_message_board_api_creates_post_and_calls_agent(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    async def fake_reply(post):
        return f"Hermes reply for {post['title']}"

    monkeypatch.setattr(dashboard_app, "generate_message_board_agent_reply", fake_reply)

    async def scenario():
        response = await dashboard_app.create_message_board_post_endpoint(
            FakeRequest({"title": "Forum loop", "body": "Reply here please", "author": "mojo"})
        )
        listing = await dashboard_app.get_message_board_posts_endpoint(FakeRequest())
        return response, listing

    response, listing_response = asyncio.run(scenario())
    assert response.status_code == 201
    created = _decode(response)
    assert created["status"] == "answered"
    assert created["messages"][-1]["role"] == "assistant"
    assert created["messages"][-1]["content"] == "Hermes reply for Forum loop"

    listing = _decode(listing_response)
    assert listing["posts"][0]["id"] == created["id"]
    assert listing["posts"][0]["status"] == "answered"


def test_message_board_api_replies_in_existing_thread_context(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)
    post = dashboard_app.create_message_board_post(
        title="Threaded forum",
        body="First post",
        author="mojo",
        agent_reply="First Hermes reply",
    )

    seen = {}

    async def fake_reply(thread):
        seen["messages"] = [msg["content"] for msg in thread["messages"]]
        return "Second Hermes reply"

    monkeypatch.setattr(dashboard_app, "generate_message_board_agent_reply", fake_reply)

    class PathRequest(FakeRequest):
        def __init__(self, payload, post_id):
            super().__init__(payload)
            self.path_params = {"post_id": post_id}

    async def scenario():
        return await dashboard_app.create_message_board_message_endpoint(
            PathRequest(
                {"content": "Follow-up from user", "author": "mojo", "ask_agent": True},
                post["id"],
            )
        )

    response = asyncio.run(scenario())
    assert response.status_code == 201
    updated = _decode(response)
    assert [msg["role"] for msg in updated["messages"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert seen["messages"] == ["First post", "First Hermes reply", "Follow-up from user"]
    assert updated["messages"][-1]["content"] == "Second Hermes reply"


def test_message_board_api_returns_404_for_missing_post(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setattr(dashboard_app, "HERMES_HOME", tmp_path)

    response = asyncio.run(dashboard_app.get_message_board_post_endpoint(FakeRequest(), "missing"))
    assert response.status_code == 404
    assert _decode(response)["error"] == "Post not found"


def test_message_board_routes_and_frontend_are_registered():
    route_paths = {getattr(route, "path", None) or route.args[0] for route in dashboard_app.routes}
    assert "/api/message-board" in route_paths
    assert "/api/message-board/{post_id}" in route_paths
    assert "/api/message-board/{post_id}/messages" in route_paths

    html = dashboard_source()
    assert "Message Board" in html
    assert "message-board-form" in html
    assert "/api/message-board" in html
