from pathlib import Path

from dashboard_backend.services import games_catalog


def test_games_catalog_service_uses_injected_hermes_home(tmp_path):
    game = tmp_path / "skills" / "gaming" / "stats-coach"
    game.mkdir(parents=True)
    (game / "SKILL.md").write_text(
        "---\n"
        "name: stats-coach\n"
        "description: Strategy analytics for games.\n"
        "tags: gaming, stats, coach\n"
        "dashboard:\n"
        "  watch_url: /stats/\n"
        "  launch_label: Open Stats\n"
        "---\n"
        "# Stats Coach\n",
        encoding="utf-8",
    )

    catalog = games_catalog.get_games_catalog(hermes_home=tmp_path)

    assert catalog["count"] == 1
    [entry] = catalog["games"]
    assert entry["id"] == "stats-coach"
    assert entry["name"] == "Stats Coach"
    assert entry["category"] == "Analysis"
    assert entry["tags"] == ["gaming", "stats", "coach"]
    assert entry["watch_url"] == "/stats/"
    assert entry["launch_label"] == "Open Stats"
    assert entry["skill_path"] == str(game / "SKILL.md")


def test_games_catalog_service_tolerates_missing_or_invalid_frontmatter(tmp_path):
    plain = tmp_path / "skills" / "gaming" / "plain-tool"
    broken = tmp_path / "skills" / "gaming" / "broken-tool"
    hidden = tmp_path / "skills" / "gaming" / ".hidden"
    plain.mkdir(parents=True)
    broken.mkdir(parents=True)
    hidden.mkdir(parents=True)
    (plain / "SKILL.md").write_text("# Plain Tool\n", encoding="utf-8")
    (broken / "SKILL.md").write_text("---\nnot: [valid\n---\n# Broken\n", encoding="utf-8")

    catalog = games_catalog.get_games_catalog(hermes_home=tmp_path)

    assert catalog["count"] == 2
    assert [entry["id"] for entry in catalog["games"]] == ["broken-tool", "plain-tool"]
    assert all(entry["category"] == "Tool" for entry in catalog["games"])


def test_games_catalog_service_does_not_import_app_py():
    service_source = Path(games_catalog.__file__).read_text(encoding="utf-8")

    assert "import app" not in service_source
    assert "from app" not in service_source
