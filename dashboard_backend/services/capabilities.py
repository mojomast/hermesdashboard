"""Read-only inventory of locally declared Hermes capabilities.

The service deliberately does not import Hermes Agent modules.  Callers supply
the paths and already-loaded config needed for their installation, which keeps
discovery deterministic, offline, and straightforward to test.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml


_MAX_FILE_BYTES = 2 * 1024 * 1024
_KINDS = ("skill", "toolset", "mcp_server", "plugin")
_FALSE_STRINGS = {"0", "false", "no", "off"}
_SAFE_TRUST_KEYS = {
    "audited",
    "sandboxed",
    "signed",
    "signature_verified",
    "trusted",
    "risk",
    "level",
    "source",
}


def _read_text(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _yaml_mapping(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    if text is None:
        return {}
    try:
        value = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}
    return value if isinstance(value, dict) else {}


def _frontmatter(path: Path) -> dict[str, Any]:
    text = _read_text(path)
    if not text or not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) != 3:
        return {}
    try:
        value = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return value if isinstance(value, dict) else {}


def _text(value: Any, maximum: int = 1000) -> str:
    return str(value).strip()[:maximum] if isinstance(value, (str, int, float)) else ""


def _names(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return sorted({_text(item, 200) for item in value if _text(item, 200)}, key=str.casefold)


def _name_set(value: Any) -> set[str]:
    return set(_names(value))


def _safe_trust(*values: Any) -> dict[str, Any]:
    """Project declared trust metadata without copying arbitrary values."""

    result: dict[str, Any] = {}
    for value in values:
        if isinstance(value, str):
            result.setdefault("level", value[:100])
            continue
        if not isinstance(value, Mapping):
            continue
        for key in _SAFE_TRUST_KEYS:
            item = value.get(key)
            if isinstance(item, bool):
                result[key] = item
            elif isinstance(item, (str, int, float)):
                result[key] = str(item)[:100]
    return dict(sorted(result.items()))


def _source(path: Path, source_kind: str) -> dict[str, str]:
    return {"kind": source_kind, "path": str(path)}


def _row(
    kind: str,
    name: str,
    description: str,
    capability_names: Iterable[str],
    states: Mapping[str, bool | None],
    source: Mapping[str, str],
    *,
    security: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{kind}:{name}",
        "kind": kind,
        "name": name,
        "description": description,
        "capability_names": sorted(set(capability_names), key=str.casefold),
        "states": {
            state: states.get(state)
            for state in ("installed", "enabled", "configured", "available")
        },
        "source": dict(source),
        "security": dict(security or {}),
        "details": dict(details or {}),
    }


def _discover_skills(
    roots: Iterable[Path], config: Mapping[str, Any], platform: str | None
) -> list[dict[str, Any]]:
    skills_cfg = config.get("skills") if isinstance(config.get("skills"), Mapping) else {}
    disabled = _name_set(skills_cfg.get("disabled"))
    platform_disabled = skills_cfg.get("platform_disabled")
    if platform and isinstance(platform_disabled, Mapping):
        disabled |= _name_set(platform_disabled.get(platform))

    rows = []
    for root in sorted({Path(item) for item in roots}, key=lambda path: str(path).casefold()):
        try:
            manifests = sorted(root.rglob("SKILL.md"), key=lambda path: str(path).casefold())
        except OSError:
            continue
        for manifest in manifests:
            metadata = _frontmatter(manifest)
            if not metadata:
                continue
            name = _text(metadata.get("name") or manifest.parent.name, 200)
            if not name:
                continue
            hermes = metadata.get("metadata")
            hermes = hermes.get("hermes") if isinstance(hermes, Mapping) else {}
            hermes = hermes if isinstance(hermes, Mapping) else {}
            platforms = _names(metadata.get("platforms"))
            available = None if not platform else not platforms or platform in platforms
            configured = name in disabled
            rows.append(
                _row(
                    "skill",
                    name,
                    _text(metadata.get("description")),
                    _names(metadata.get("tags")) + _names(hermes.get("tags")),
                    {
                        "installed": True,
                        "enabled": name not in disabled,
                        "configured": configured,
                        "available": available,
                    },
                    _source(manifest, "skill_manifest"),
                    security=_safe_trust(metadata.get("trust"), metadata.get("security"), hermes.get("security")),
                    details={
                        "category": _text(metadata.get("category") or hermes.get("category"), 100),
                        "platforms": platforms,
                        "skill_id": manifest.parent.name,
                        "version": _text(metadata.get("version"), 100),
                    },
                )
            )
    return rows


class _Unevaluated(Exception):
    pass


def _literal(node: ast.AST, names: Mapping[str, Any]) -> Any:
    """Evaluate data-only AST nodes used by the static TOOLSETS declaration."""

    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.List):
        return [_literal(item, names) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_literal(item, names) for item in node.elts)
    if isinstance(node, ast.Set):
        return {_literal(item, names) for item in node.elts}
    if isinstance(node, ast.Dict):
        return {_literal(key, names): _literal(value, names) for key, value in zip(node.keys, node.values)}
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal(node.left, names) + _literal(node.right, names)
    raise _Unevaluated


def load_toolsets_file(path: Path) -> dict[str, Any]:
    """Read a Python ``TOOLSETS`` constant without importing or executing it."""

    text = _read_text(Path(path))
    if text is None:
        return {}
    try:
        tree = ast.parse(text, filename=str(path))
    except (SyntaxError, ValueError):
        return {}
    names: dict[str, Any] = {}
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        value_node = statement.value
        if value_node is None:
            continue
        try:
            value = _literal(value_node, names)
        except (TypeError, _Unevaluated):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                names[target.id] = value
    value = names.get("TOOLSETS")
    return value if isinstance(value, dict) else {}


def _discover_toolsets(
    toolsets: Mapping[str, Any], source_path: Path | None, config: Mapping[str, Any]
) -> list[dict[str, Any]]:
    platform_cfg = config.get("platform_toolsets")
    configured_names: set[str] = set()
    if isinstance(platform_cfg, Mapping):
        for value in platform_cfg.values():
            configured_names |= _name_set(value)
    agent_cfg = config.get("agent") if isinstance(config.get("agent"), Mapping) else {}
    disabled = _name_set(agent_cfg.get("disabled_toolsets"))
    rows = []
    for raw_name, definition in toolsets.items():
        if not isinstance(definition, Mapping):
            continue
        name = _text(raw_name, 200)
        if not name:
            continue
        explicitly_configured = name in configured_names or name in disabled
        enabled = False if name in disabled else (True if name in configured_names else None)
        rows.append(
            _row(
                "toolset",
                name,
                _text(definition.get("description")),
                _names(definition.get("tools")),
                {
                    "installed": True,
                    "enabled": enabled,
                    "configured": explicitly_configured,
                    "available": True,
                },
                _source(source_path, "toolsets_file") if source_path else {"kind": "provided_data"},
                security=_safe_trust(definition.get("trust"), definition.get("security")),
                details={"includes": _names(definition.get("includes"))},
            )
        )
    return rows


def _enabled_flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in _FALSE_STRINGS
    return value is not False and value != 0


def _discover_mcp(servers: Mapping[str, Any], source_path: Path | None) -> list[dict[str, Any]]:
    rows = []
    for raw_name, definition in servers.items():
        if not isinstance(definition, Mapping):
            continue
        name = _text(raw_name, 200)
        if not name:
            continue
        credential_fields = []
        for field in ("env", "headers"):
            value = definition.get(field)
            if isinstance(value, Mapping) and value:
                credential_fields.append(field)
        transport = "http" if any(key in definition for key in ("url", "http_url")) else "stdio"
        rows.append(
            _row(
                "mcp_server",
                name,
                _text(definition.get("description")),
                _names(definition.get("tools")) + _names(definition.get("capabilities")),
                {
                    "installed": None,
                    "enabled": _enabled_flag(definition.get("enabled", True)),
                    "configured": True,
                    "available": None,
                },
                _source(source_path, "config_file") if source_path else {"kind": "provided_config"},
                security={
                    "credential_fields": credential_fields,
                    "has_declared_credentials": bool(credential_fields),
                    **_safe_trust(definition.get("trust"), definition.get("security")),
                },
                details={"transport": transport},
            )
        )
    return rows


def _required_env_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, Mapping):
            item = item.get("name")
        name = _text(item, 200)
        if name:
            names.append(name)
    return sorted(set(names), key=str.casefold)


def _discover_plugins(roots: Iterable[Path], config: Mapping[str, Any]) -> list[dict[str, Any]]:
    plugins_cfg = config.get("plugins") if isinstance(config.get("plugins"), Mapping) else {}
    enabled_names = _name_set(plugins_cfg.get("enabled"))
    disabled_names = _name_set(plugins_cfg.get("disabled"))
    entries = plugins_cfg.get("entries") if isinstance(plugins_cfg.get("entries"), Mapping) else {}
    rows = []
    for root in sorted({Path(item) for item in roots}, key=lambda path: str(path).casefold()):
        try:
            manifests = sorted(root.rglob("plugin.yaml"), key=lambda path: str(path).casefold())
        except OSError:
            continue
        for manifest_path in manifests:
            manifest = _yaml_mapping(manifest_path)
            name = _text(manifest.get("name") or manifest_path.parent.name, 200)
            if not manifest or not name:
                continue
            relative_key = ""
            try:
                relative_key = str(manifest_path.parent.relative_to(root))
            except ValueError:
                pass
            aliases = {name, relative_key}
            disabled = bool(aliases & disabled_names)
            enabled = bool(aliases & enabled_names) and not disabled
            entry = entries.get(name) if isinstance(entries, Mapping) else {}
            entry = entry if isinstance(entry, Mapping) else {}
            declared = _names(manifest.get("capabilities"))
            granted = _name_set(entry.get("granted_capabilities")) & set(declared)
            required_env = _required_env_names(manifest.get("requires_env"))
            capability_names = declared + [f"hook:{item}" for item in _names(manifest.get("hooks"))]
            capability_names += [f"tool:{item}" for item in _names(manifest.get("tools"))]
            configured = bool(aliases & (enabled_names | disabled_names))
            rows.append(
                _row(
                    "plugin",
                    name,
                    _text(manifest.get("description")),
                    capability_names,
                    {
                        "installed": True,
                        "enabled": enabled,
                        "configured": configured,
                        "available": None if enabled and required_env else enabled,
                    },
                    _source(manifest_path, "plugin_manifest"),
                    security={
                        "declared_capabilities": declared,
                        "granted_capabilities": sorted(granted, key=str.casefold),
                        "required_env_names": required_env,
                        **_safe_trust(manifest.get("trust"), manifest.get("security")),
                    },
                    details={
                        "kind": _text(manifest.get("kind"), 100),
                        "version": _text(manifest.get("version"), 100),
                    },
                )
            )
    return rows


def inventory_capabilities(
    *,
    skill_roots: Iterable[Path] = (),
    toolsets: Mapping[str, Any] | None = None,
    toolsets_path: Path | None = None,
    mcp_servers: Mapping[str, Any] | None = None,
    mcp_config_path: Path | None = None,
    plugin_roots: Iterable[Path] = (),
    config: Mapping[str, Any] | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    """Return normalized rows and counts using only supplied local inputs."""

    safe_config = config if isinstance(config, Mapping) else {}
    if toolsets is None:
        toolsets = load_toolsets_file(Path(toolsets_path)) if toolsets_path else {}
    if not isinstance(toolsets, Mapping):
        toolsets = {}
    if mcp_servers is None:
        if mcp_config_path:
            mcp_document = _yaml_mapping(Path(mcp_config_path))
            mcp_servers = mcp_document.get("mcp_servers", {})
        else:
            mcp_servers = safe_config.get("mcp_servers", {})
    if not isinstance(mcp_servers, Mapping):
        mcp_servers = {}

    rows = [
        *_discover_skills(skill_roots, safe_config, platform),
        *_discover_toolsets(toolsets, Path(toolsets_path) if toolsets_path else None, safe_config),
        *_discover_mcp(mcp_servers, Path(mcp_config_path) if mcp_config_path else None),
        *_discover_plugins(plugin_roots, safe_config),
    ]
    rows.sort(key=lambda row: (_KINDS.index(row["kind"]), row["name"].casefold(), row["source"].get("path", "")))
    by_kind = {kind: sum(row["kind"] == kind for row in rows) for kind in _KINDS}
    state_counts = {
        state: {
            "true": sum(row["states"][state] is True for row in rows),
            "false": sum(row["states"][state] is False for row in rows),
            "unknown": sum(row["states"][state] is None for row in rows),
        }
        for state in ("installed", "enabled", "configured", "available")
    }
    return {"rows": rows, "summary": {"total": len(rows), "by_kind": by_kind, "states": state_counts}}


def inventory_json(**kwargs: Any) -> str:
    """Serialize an inventory deterministically for API responses or caching."""

    return json.dumps(inventory_capabilities(**kwargs), sort_keys=True, separators=(",", ":"))
