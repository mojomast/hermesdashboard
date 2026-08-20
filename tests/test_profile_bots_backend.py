import asyncio
import json
import os
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import app as dashboard_app
from dashboard_backend.routes import bots as bot_routes
from dashboard_backend.services import bots


class FakeRequest:
    def __init__(self, body=b"{}", path_params=None, headers=None):
        self._body = body
        self.path_params = path_params or {}
        self.headers = headers or {}

    async def body(self):
        return self._body


def payload(response):
    return json.loads(response.body)


def profile(name, path, **values):
    defaults = dict(
        is_default=name == "default",
        display_name="",
        description="",
        model="model-a",
        provider="provider-a",
        skill_count=2,
    )
    defaults.update(values)
    return SimpleNamespace(name=name, path=path, **defaults)


def test_list_bots_uses_official_profiles_and_only_returns_safe_fields(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "profile.yaml").write_text(
        "description: useful\ndisplay_name: Helper\nui_meta:\n  hermes-bots:\n    color: '#112233'\n    hidden: true\n    auth: secret\n",
        encoding="utf-8",
    )
    api = SimpleNamespace(list_profiles=lambda: [profile("default", home)])

    listed = bots.list_bots(profiles_api=api)

    assert listed == [{
        "name": "default", "display_name": "Helper", "title": "Helper",
        "description": "useful", "model": "model-a", "provider": "provider-a",
        "color": "#112233", "shape": "circle", "hidden": True,
        "is_default": True, "skill_count": 2, "avatar_url": None,
        "avatar_version": None,
    }]
    assert "auth" not in listed[0]


def test_create_bot_validates_and_calls_official_clone_api(tmp_path):
    home = tmp_path / ".hermes"
    created = home / "profiles" / "writer"
    home.mkdir(parents=True)
    profiles = [profile("default", home)]
    calls = []

    def create_profile(name, **kwargs):
        calls.append((name, kwargs))
        created.mkdir(parents=True)
        profiles.append(profile(name, created, is_default=False))
        return created

    api = SimpleNamespace(list_profiles=lambda: profiles, create_profile=create_profile)
    result = bots.create_bot(
        {"name": "writer", "display_name": "Writer", "description": "Writes.", "soul": "Be exact.", "color": "#AABBCC"},
        profiles_api=api,
        restart=lambda: "restart failed",
    )

    assert calls == [("writer", {"clone_from": "default", "clone_config": True, "no_alias": True})]
    assert result["gateway_restarted"] is False
    assert result["restart_error"] == "restart failed"
    assert (created / "SOUL.md").read_text() == "Be exact.\n"
    raw = (created / "profile.yaml").read_text()
    assert "title: Writer" in raw
    assert "color: '#aabbcc'" in raw
    assert "groups: []" in raw

    with pytest.raises(ValueError):
        bots.create_bot({"name": "../bad"}, profiles_api=api, restart=lambda: None)
    with pytest.raises(ValueError):
        bots.create_bot({"name": "valid", "description": "x" * 501}, profiles_api=api, restart=lambda: None)


def test_bot_route_contracts_map_validation_and_soft_delete():
    bad = asyncio.run(
        bot_routes.create_bot_endpoint(
            FakeRequest(b"not-json"), create_bot=lambda data: data
        )
    )
    assert bad.status_code == 400

    deleted = asyncio.run(
        bot_routes.delete_bot_endpoint(
            FakeRequest(path_params={"name": "writer"}),
            hide_bot=lambda name: {"name": name, "hidden": True},
        )
    )
    assert payload(deleted)["bot"]["hidden"] is True


def image_bytes(format="JPEG", size=(900, 600), **save_options):
    output = BytesIO()
    Image.new("RGB", size, "#123456").save(output, format=format, **save_options)
    return output.getvalue()


def test_bot_detail_is_editable_but_field_limited(tmp_path):
    home = tmp_path / "profile"
    home.mkdir()
    (home / "profile.yaml").write_text(
        "display_name: Writer\ndescription: safe\napi_key: secret\nui_meta:\n  hermes-bots:\n    color: '#abcdef'\n",
        encoding="utf-8",
    )
    (home / "SOUL.md").write_text("Be precise.\n", encoding="utf-8")
    api = SimpleNamespace(list_profiles=lambda: [profile("writer", home)])

    detail = bots.get_bot("writer", profiles_api=api)

    assert detail["soul"] == "Be precise."
    assert detail["display_name"] == "Writer"
    assert "api_key" not in detail
    assert "ui_meta" not in detail


def test_avatar_is_normalized_projected_and_deleted(tmp_path):
    home = tmp_path / "profile"
    home.mkdir()
    api = SimpleNamespace(list_profiles=lambda: [profile("writer", home)])
    raw = image_bytes(exif=b"Exif\x00\x00")

    projected = bots.save_avatar("writer", raw, content_type="image/jpeg", profiles_api=api)
    avatar = home / "assets" / "avatar.png"

    assert avatar.stat().st_mode & 0o777 == 0o644
    with Image.open(avatar) as normalized:
        assert normalized.format == "PNG"
        assert max(normalized.size) == 512
        assert not normalized.info.get("exif")
    assert projected["avatar_version"]
    assert projected["avatar_url"].endswith(f"?v={projected['avatar_version']}")
    path, digest = bots.get_avatar("writer", profiles_api=api)
    assert path == avatar
    assert digest.startswith(projected["avatar_version"])
    assert bots.delete_avatar("writer", profiles_api=api)["avatar_url"] is None
    assert not avatar.exists()


def test_avatar_rejects_invalid_oversized_multiframe_and_linked_paths(tmp_path):
    home = tmp_path / "profile"
    home.mkdir()
    api = SimpleNamespace(list_profiles=lambda: [profile("writer", home)])
    with pytest.raises(ValueError):
        bots.save_avatar("writer", b"not an image", content_type="image/png", profiles_api=api)
    with pytest.raises(ValueError):
        bots.save_avatar("writer", b"x" * (bots.MAX_AVATAR_BYTES + 1), content_type="image/png", profiles_api=api)
    with pytest.raises(ValueError):
        bots.save_avatar("writer", image_bytes(size=(2049, 1)), content_type="image/jpeg", profiles_api=api)

    animated = BytesIO()
    frames = [Image.new("RGB", (10, 10), "red"), Image.new("RGB", (10, 10), "blue")]
    frames[0].save(animated, format="WEBP", save_all=True, append_images=frames[1:])
    with pytest.raises(ValueError):
        bots.save_avatar("writer", animated.getvalue(), content_type="image/webp", profiles_api=api)

    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, home / "assets")
    with pytest.raises(ValueError):
        bots.save_avatar("writer", image_bytes(), content_type="image/jpeg", profiles_api=api)


def test_avatar_route_headers_body_bound_and_delete_contract(tmp_path):
    avatar = tmp_path / "avatar.png"
    avatar.write_bytes(image_bytes(format="PNG", size=(8, 8)))
    request = FakeRequest(path_params={"name": "writer"})
    response = asyncio.run(bot_routes.get_avatar_endpoint(
        request, get_avatar=lambda name: (avatar, "abc123")
    ))
    assert response.media_type == "image/png"
    assert response.headers["etag"] == '"abc123"'
    assert response.headers["cache-control"].endswith("immutable")
    assert response.headers["x-content-type-options"] == "nosniff"

    too_large = asyncio.run(bot_routes.put_avatar_endpoint(
        FakeRequest(
            b"x" * (bot_routes.MAX_AVATAR_BODY + 1),
            {"name": "writer"},
            {"content-type": "image/png"},
        ),
        save_avatar=lambda name, raw, content_type: {},
    ))
    assert too_large.status_code == 400

    deleted = asyncio.run(bot_routes.delete_avatar_endpoint(
        request, delete_avatar=lambda name: {"name": name, "avatar_url": None}
    ))
    assert payload(deleted)["deleted"] is True


def test_bot_routes_are_registered():
    routes = set()
    for route in dashboard_app.routes:
        path = getattr(route, "path", None) or (route.args[0] if getattr(route, "args", None) else None)
        methods = getattr(route, "methods", None)
        if methods is None:
            methods = getattr(route, "kwargs", {}).get("methods", ["GET"])
        routes.add((path, tuple(sorted(methods))))
    assert any(path == "/api/bots" and "GET" in methods for path, methods in routes)
    assert ("/api/bots", ("POST",)) in routes
    assert any(path == "/api/bots/{name}" and "GET" in methods for path, methods in routes)
    assert ("/api/bots/{name}/avatar", ("PUT",)) in routes
    assert ("/api/bots/{name}/avatar", ("DELETE",)) in routes
    assert ("/api/bots/{name}", ("DELETE",)) in routes
    assert ("/api/bot-rooms/shared/messages/stream", ("POST",)) in routes
    assert ("/api/bot-rooms/{room_id}", ("PUT",)) in routes
