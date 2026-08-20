"""Safe profile-backed Hermes bot management."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import warnings
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from PIL import Image, ImageOps, UnidentifiedImageError


PROFILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
BOT_SHAPES = {"circle", "diamond", "hexagon", "square"}
MAX_DISPLAY_NAME = 64
MAX_DESCRIPTION = 500
MAX_SOUL = 20_000
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_DIMENSION = 2048
MAX_AVATAR_PIXELS = 4_000_000
AVATAR_OUTPUT_SIZE = 512
BOT_META_KEY = "hermes-bots"


def validate_profile_slug(name: Any, *, allow_default: bool = True) -> str:
    value = str(name or "").strip()
    if not PROFILE_RE.fullmatch(value) or (value == "default" and not allow_default):
        raise ValueError("Invalid profile name")
    return value


def _profiles_api(profiles_api=None):
    if profiles_api is not None:
        return profiles_api
    from hermes_cli import profiles

    return profiles


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{field} must be at most {maximum} characters")
    return value


def validate_bot_fields(data: Any, *, creating: bool = False) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    allowed = {"display_name", "description", "soul", "color"}
    if creating:
        allowed.add("name")
    else:
        allowed.add("hidden")
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"Unsupported fields: {', '.join(unknown)}")

    result = {}
    if creating:
        result["name"] = validate_profile_slug(data.get("name"), allow_default=False)
    for field, maximum in (
        ("display_name", MAX_DISPLAY_NAME),
        ("description", MAX_DESCRIPTION),
        ("soul", MAX_SOUL),
    ):
        if field in data:
            result[field] = _text(data[field], field, maximum)
    if "color" in data:
        color = _text(data["color"], "color", 7)
        if color and not COLOR_RE.fullmatch(color):
            raise ValueError("color must be a six-digit hex color")
        result["color"] = color.lower()
    if "hidden" in data:
        if not isinstance(data["hidden"], bool):
            raise ValueError("hidden must be a boolean")
        result["hidden"] = data["hidden"]
    return result


def _read_yaml_dict(path: Path) -> dict:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() and not path.is_symlink() else {}
    except (OSError, yaml.YAMLError):
        value = {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _write_bot_metadata(profile_dir: Path, fields: dict) -> None:
    path = profile_dir / "profile.yaml"
    metadata = _read_yaml_dict(path)
    if "display_name" in fields:
        if fields["display_name"]:
            metadata["display_name"] = fields["display_name"]
        else:
            metadata.pop("display_name", None)
    if "description" in fields:
        metadata["description"] = fields["description"]
        metadata["description_auto"] = False

    ui_meta = metadata.get("ui_meta")
    if not isinstance(ui_meta, dict):
        ui_meta = {}
    bot_meta = ui_meta.get(BOT_META_KEY)
    if not isinstance(bot_meta, dict):
        bot_meta = {}
    if "display_name" in fields:
        bot_meta["title"] = fields["display_name"]
    if "color" in fields:
        bot_meta["color"] = fields["color"]
    if "hidden" in fields:
        bot_meta["hidden"] = fields["hidden"]
    bot_meta.setdefault("title", fields.get("display_name") or fields.get("name") or profile_dir.name)
    bot_meta.setdefault("color", "#60a5fa")
    bot_meta.setdefault("shape", "circle")
    bot_meta.setdefault("hidden", False)
    bot_meta.setdefault("groups", [])
    ui_meta[BOT_META_KEY] = bot_meta
    metadata["ui_meta"] = ui_meta
    _atomic_write(path, yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True))


def _avatar_path(profile_dir: Path, *, create_parent: bool = False) -> Path:
    if profile_dir.is_symlink() or not profile_dir.is_dir():
        raise ValueError("Profile directory is not safe")
    assets = profile_dir / "assets"
    if assets.exists() and (assets.is_symlink() or not assets.is_dir()):
        raise ValueError("Avatar assets directory is not safe")
    if create_parent:
        assets.mkdir(mode=0o755, parents=False, exist_ok=True)
    avatar = assets / "avatar.png"
    if avatar.is_symlink():
        raise ValueError("Avatar path is not safe")
    return avatar


def _avatar_version(profile_dir: Path) -> str | None:
    try:
        avatar = _avatar_path(profile_dir)
        if not avatar.is_file():
            return None
        return sha256(avatar.read_bytes()).hexdigest()[:16]
    except (OSError, ValueError):
        return None


def _bot_projection(profile) -> dict:
    profile_dir = Path(profile.path)
    metadata = _read_yaml_dict(profile_dir / "profile.yaml")
    ui_meta = metadata.get("ui_meta") if isinstance(metadata.get("ui_meta"), dict) else {}
    bot_meta = ui_meta.get(BOT_META_KEY) if isinstance(ui_meta.get(BOT_META_KEY), dict) else {}
    display_name = str(metadata.get("display_name") or getattr(profile, "display_name", "") or "").strip()
    title = str(bot_meta.get("title") or display_name or profile.name).strip()[:MAX_DISPLAY_NAME]
    description = str(metadata.get("description") or getattr(profile, "description", "") or "").strip()
    shape = str(bot_meta.get("shape") or "circle").strip()[:32]
    if shape not in BOT_SHAPES:
        shape = "circle"
    color = str(bot_meta.get("color") or "").strip()
    if color and not COLOR_RE.fullmatch(color):
        color = ""
    avatar_version = _avatar_version(profile_dir)
    result = {
        "name": str(profile.name),
        "display_name": display_name[:MAX_DISPLAY_NAME] or title,
        "title": title,
        "description": description[:MAX_DESCRIPTION],
        "model": getattr(profile, "model", None),
        "provider": getattr(profile, "provider", None),
        "color": color,
        "shape": shape,
        "hidden": bool(bot_meta.get("hidden", False)),
        "is_default": bool(getattr(profile, "is_default", profile.name == "default")),
        "skill_count": max(0, int(getattr(profile, "skill_count", 0) or 0)),
        "avatar_version": avatar_version,
    }
    result["avatar_url"] = (
        f"/api/bots/{quote(str(profile.name), safe='')}/avatar?v={avatar_version}"
        if avatar_version else None
    )
    return result


def list_bots(*, profiles_api=None) -> list[dict]:
    profiles = _profiles_api(profiles_api).list_profiles()
    bots = [_bot_projection(profile) for profile in profiles]
    return sorted(bots, key=lambda bot: (not bot["is_default"], bot["name"]))


def get_bot(name: Any, *, profiles_api=None) -> dict:
    name = validate_profile_slug(name)
    profile = _profile(name, profiles_api=profiles_api)
    profile_dir = Path(profile.path)
    soul_path = profile_dir / "SOUL.md"
    soul = ""
    if soul_path.is_file() and not soul_path.is_symlink():
        try:
            soul = soul_path.read_text(encoding="utf-8")[:MAX_SOUL].rstrip("\n")
        except (OSError, UnicodeDecodeError):
            soul = ""
    return {**_bot_projection(profile), "soul": soul}


def save_avatar(
    name: Any,
    raw: bytes,
    *,
    content_type: str | None = None,
    profiles_api=None,
) -> dict:
    name = validate_profile_slug(name)
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("Avatar image is required")
    if len(raw) > MAX_AVATAR_BYTES:
        raise ValueError("Avatar image may be at most 2 MiB")
    profile = _profile(name, profiles_api=profiles_api)
    expected_format = {
        "image/png": "PNG",
        "image/jpeg": "JPEG",
        "image/webp": "WEBP",
    }.get(str(content_type or "").split(";", 1)[0].strip().lower())
    if expected_format is None:
        raise ValueError("Avatar Content-Type must be image/png, image/jpeg, or image/webp")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ValueError("Avatar must be a PNG, JPEG, or WebP image")
                if source.format != expected_format:
                    raise ValueError("Avatar Content-Type does not match the image data")
                if int(getattr(source, "n_frames", 1)) != 1:
                    raise ValueError("Animated avatars are not supported")
                width, height = source.size
                if width > MAX_AVATAR_DIMENSION or height > MAX_AVATAR_DIMENSION or width * height > MAX_AVATAR_PIXELS:
                    raise ValueError("Avatar dimensions are too large")
                source.seek(0)
                transposed = ImageOps.exif_transpose(source)
                mode = "RGBA" if "A" in transposed.getbands() else "RGB"
                converted = transposed.convert(mode)
                converted.thumbnail((AVATAR_OUTPUT_SIZE, AVATAR_OUTPUT_SIZE), Image.Resampling.LANCZOS)
                clean = Image.new(mode, converted.size)
                clean.paste(converted)
                output = BytesIO()
                clean.save(output, format="PNG", optimize=True)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError) as exc:
        raise ValueError("Invalid avatar image") from exc

    avatar = _avatar_path(Path(profile.path), create_parent=True)
    fd, temporary = tempfile.mkstemp(prefix=".avatar.", dir=str(avatar.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(output.getvalue())
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        if avatar.is_symlink():
            raise ValueError("Avatar path is not safe")
        os.replace(temporary, avatar)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return _bot_projection(profile)


def get_avatar(name: Any, *, profiles_api=None) -> tuple[Path, str]:
    name = validate_profile_slug(name)
    profile = _profile(name, profiles_api=profiles_api)
    avatar = _avatar_path(Path(profile.path))
    if not avatar.is_file():
        raise FileNotFoundError(f"Avatar for profile '{name}' does not exist")
    digest = sha256(avatar.read_bytes()).hexdigest()
    return avatar, digest


def delete_avatar(name: Any, *, profiles_api=None) -> dict:
    name = validate_profile_slug(name)
    profile = _profile(name, profiles_api=profiles_api)
    avatar = _avatar_path(Path(profile.path))
    try:
        avatar.unlink()
    except FileNotFoundError:
        pass
    return _bot_projection(profile)


def _profile(profile_name: str, *, profiles_api=None):
    for profile in _profiles_api(profiles_api).list_profiles():
        if profile.name == profile_name:
            return profile
    raise FileNotFoundError(f"Profile '{profile_name}' does not exist")


def restart_gateway(*, runner=subprocess.run) -> str | None:
    try:
        result = runner(
            ["systemctl", "--user", "restart", "hermes-gateway.service"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception as exc:
        return str(exc)[:500]
    if result.returncode == 0:
        return None
    return (result.stderr or result.stdout or f"systemctl exited {result.returncode}").strip()[:500]


def create_bot(data: Any, *, profiles_api=None, restart=restart_gateway) -> dict:
    fields = validate_bot_fields(data, creating=True)
    api = _profiles_api(profiles_api)
    profile_dir = Path(
        api.create_profile(
            fields["name"],
            clone_from="default",
            clone_config=True,
            no_alias=True,
        )
    )
    _write_bot_metadata(profile_dir, fields)
    if "soul" in fields:
        _atomic_write(profile_dir / "SOUL.md", fields["soul"] + ("\n" if fields["soul"] else ""))
    restart_error = restart()
    return {
        "bot": _bot_projection(_profile(fields["name"], profiles_api=api)),
        "gateway_restarted": restart_error is None,
        "restart_error": restart_error,
    }


def update_bot(name: Any, data: Any, *, profiles_api=None) -> dict:
    name = validate_profile_slug(name)
    fields = validate_bot_fields(data)
    profile = _profile(name, profiles_api=profiles_api)
    profile_dir = Path(profile.path)
    _write_bot_metadata(profile_dir, {**fields, "name": name})
    if "soul" in fields:
        _atomic_write(profile_dir / "SOUL.md", fields["soul"] + ("\n" if fields["soul"] else ""))
    return _bot_projection(_profile(name, profiles_api=profiles_api))


def hide_bot(name: Any, *, profiles_api=None) -> dict:
    return update_bot(name, {"hidden": True}, profiles_api=profiles_api)
