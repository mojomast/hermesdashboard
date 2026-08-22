import json
from pathlib import Path

from dashboard_backend.services.capabilities import (
    inventory_capabilities,
    inventory_json,
    load_toolsets_file,
)


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_inventory_normalizes_all_local_capability_kinds(tmp_path):
    skills = tmp_path / "skills"
    plugins = tmp_path / "plugins"
    write(
        skills / "development" / "alpha" / "SKILL.md",
        """---
name: alpha
description: Alpha skill.
version: 1.2
platforms: [linux]
metadata:
  hermes:
    category: development
    tags: [testing, local]
    security:
      audited: true
---
# Alpha
""",
    )
    write(
        plugins / "utilities" / "sample" / "plugin.yaml",
        """name: sample
version: 2.0
description: Sample plugin.
kind: utility
hooks: [pre_tool_call]
tools: [sample_tool]
capabilities: [tools.override]
requires_env:
  - name: SAMPLE_TOKEN
    password: true
security:
  sandboxed: false
""",
    )
    config = {
        "skills": {"disabled": ["alpha"]},
        "platform_toolsets": {"cli": ["web"]},
        "mcp_servers": {
            "docs": {
                "url": "https://example.invalid/mcp?token=do-not-leak",
                "headers": {"Authorization": "Bearer very-secret"},
                "tools": ["lookup"],
            }
        },
        "plugins": {
            "enabled": ["sample"],
            "entries": {
                "sample": {
                    "granted_capabilities": ["tools.override"],
                    "private_token": "do-not-leak",
                }
            },
        },
    }

    result = inventory_capabilities(
        skill_roots=[skills],
        toolsets={
            "web": {
                "description": "Web tools.",
                "tools": ["web_extract", "web_search"],
                "includes": [],
            }
        },
        plugin_roots=[plugins],
        config=config,
        platform="linux",
    )

    assert [row["id"] for row in result["rows"]] == [
        "skill:alpha",
        "toolset:web",
        "mcp_server:docs",
        "plugin:sample",
    ]
    assert all(set(row) == {
        "id", "kind", "name", "description", "capability_names", "states",
        "source", "security", "details",
    } for row in result["rows"])
    skill, toolset, mcp, plugin = result["rows"]
    assert skill["states"] == {
        "installed": True, "enabled": False, "configured": True, "available": True
    }
    assert skill["security"] == {"audited": True}
    assert toolset["capability_names"] == ["web_extract", "web_search"]
    assert toolset["states"]["enabled"] is True
    assert mcp["details"] == {"transport": "http"}
    assert mcp["security"] == {
        "credential_fields": ["headers"], "has_declared_credentials": True
    }
    assert plugin["capability_names"] == [
        "hook:pre_tool_call", "tool:sample_tool", "tools.override"
    ]
    assert plugin["security"]["granted_capabilities"] == ["tools.override"]
    assert plugin["security"]["required_env_names"] == ["SAMPLE_TOKEN"]
    assert result["summary"]["total"] == 4
    assert result["summary"]["by_kind"] == {
        "skill": 1, "toolset": 1, "mcp_server": 1, "plugin": 1
    }
    serialized = json.dumps(result)
    assert "very-secret" not in serialized
    assert "do-not-leak" not in serialized
    assert "example.invalid" not in serialized


def test_toolsets_file_is_parsed_without_executing_code(tmp_path):
    marker = tmp_path / "executed"
    path = write(
        tmp_path / "toolsets.py",
        f"""from pathlib import Path
Path({str(marker)!r}).write_text('bad')
CORE = ["terminal", "process"]
TOOLSETS = {{
    "terminal": {{
        "description": "Terminal tools.",
        "tools": CORE + ["read_terminal"],
        "includes": [],
    }}
}}
""",
    )

    assert load_toolsets_file(path)["terminal"]["tools"] == [
        "terminal", "process", "read_terminal"
    ]
    result = inventory_capabilities(toolsets_path=path)
    assert result["rows"][0]["capability_names"] == [
        "process", "read_terminal", "terminal"
    ]
    assert not marker.exists()


def test_missing_malformed_and_oversized_files_are_ignored(tmp_path):
    skills = tmp_path / "skills"
    plugins = tmp_path / "plugins"
    write(skills / "bad" / "SKILL.md", "---\nnot: [valid\n---\n")
    write(skills / "plain" / "SKILL.md", "# no frontmatter\n")
    write(plugins / "bad" / "plugin.yaml", "name: [not-a-string]\n")
    write(plugins / "huge" / "plugin.yaml", "x" * (2 * 1024 * 1024 + 1))

    result = inventory_capabilities(
        skill_roots=[skills, tmp_path / "missing-skills"],
        toolsets_path=tmp_path / "missing-toolsets.py",
        mcp_servers={"bad": "not-a-map"},
        plugin_roots=[plugins, tmp_path / "missing-plugins"],
        config={"skills": "bad", "plugins": ["bad"]},
    )

    assert result["rows"] == []
    assert result["summary"]["total"] == 0
    assert all(count == 0 for count in result["summary"]["by_kind"].values())


def test_ordering_and_json_are_deterministic(tmp_path):
    skills = tmp_path / "skills"
    for name in ("Zulu", "alpha"):
        write(
            skills / name / "SKILL.md",
            f"---\nname: {name}\ndescription: {name} description.\n---\n",
        )
    kwargs = {
        "skill_roots": [skills],
        "toolsets": {
            "zeta": {"tools": ["b", "a"]},
            "Beta": {"tools": []},
        },
        "mcp_servers": {
            "z-server": {"enabled": "off"},
            "a-server": {},
        },
    }

    first = inventory_json(**kwargs)
    second = inventory_json(**kwargs)

    assert first == second
    rows = json.loads(first)["rows"]
    assert [row["name"] for row in rows] == [
        "alpha", "Zulu", "Beta", "zeta", "a-server", "z-server"
    ]
    assert rows[-1]["states"]["enabled"] is False
