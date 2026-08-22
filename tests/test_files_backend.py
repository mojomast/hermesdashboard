import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from dashboard_backend.services.files import FileService, PathSecurityError


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "My Project"
    root.mkdir()
    return root, FileService({"Workspace": root})


def test_registry_is_stable_public_and_resolves_relative_and_legacy_paths(project):
    root, service = project
    (root / "notes.txt").write_text("hello", encoding="utf-8")
    assert service.projects() == [{"id": "workspace", "label": "Workspace"}]
    assert "root" not in service.projects()[0]
    assert service.resolve("workspace", "notes.txt") == root / "notes.txt"
    assert service.resolve_legacy(root / "notes.txt") == ("workspace", root / "notes.txt")
    assert service.resolve_legacy("My Project/notes.txt") == ("workspace", root / "notes.txt")


def test_absolute_legacy_path_prefers_the_most_specific_nested_project(tmp_path):
    parent = tmp_path / "home"
    child = parent / "project"
    child.mkdir(parents=True)
    target = child / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    service = FileService({"Home": parent, "Project": child})

    assert service.reference(target) == ("project", "notes.txt")


def test_traversal_absolute_and_symlink_escape_are_rejected(project, tmp_path):
    root, service = project
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (root / "escape").symlink_to(outside)
    for value in ("../secret.txt", outside, "escape"):
        with pytest.raises(PathSecurityError):
            service.resolve("workspace", value)
    with pytest.raises(PathSecurityError):
        service.resolve_legacy(outside)


def test_directory_listing_is_deterministic_paginated_and_reports_hidden(project):
    root, service = project
    (root / "z-dir").mkdir()
    (root / "b.txt").write_text("bb", encoding="utf-8")
    (root / "A.txt").write_text("a", encoding="utf-8")
    (root / ".hidden").write_text("h", encoding="utf-8")
    page = service.list_directory("workspace", limit=2)
    assert [entry["name"] for entry in page["entries"]] == ["z-dir", "A.txt"]
    assert page["total"] == 3 and page["has_more"] is True
    with_hidden = service.list_directory("workspace", limit=10, include_hidden=True)
    assert [entry["name"] for entry in with_hidden["entries"]] == ["z-dir", ".hidden", "A.txt", "b.txt"]
    assert with_hidden["entries"][1]["hidden"] is True
    assert {"type", "size", "mtime"} <= with_hidden["entries"][2].keys()


def test_metadata_missing_directory_and_route_target(project):
    root, service = project
    (root / "data.json").write_text("{}", encoding="utf-8")
    assert service.metadata("workspace", "")["kind"] == "directory"
    assert service.metadata("workspace", "data.json")["kind"] == "json"
    assert service.target("workspace", "data.json").path == root / "data.json"
    with pytest.raises(FileNotFoundError):
        service.metadata("workspace", "missing")
    with pytest.raises(IsADirectoryError):
        service.target("workspace", "")


def test_text_previews_are_bounded_offset_aware_and_decode_safely(project):
    root, service = project
    (root / "utf8.md").write_text("alpha beta gamma", encoding="utf-8")
    (root / "legacy.txt").write_bytes(b"caf\xe9")
    preview = service.preview("workspace", "utf8.md", max_bytes=5)
    assert preview["kind"] == "markdown"
    assert preview["content"] == "alpha"
    assert preview["truncated"] is True and preview["next_offset"] == 5
    assert service.preview("workspace", "utf8.md", offset=6, max_bytes=4)["content"] == "beta"
    legacy = service.preview("workspace", "legacy.txt")
    assert legacy["content"] == "caf\ufffd"


@pytest.mark.parametrize(
    ("name", "kind"),
    [("photo.png", "image"), ("paper.pdf", "pdf"), ("sound.mp3", "audio"), ("movie.mp4", "video"),
     ("script.py", "code"), ("readme.md", "markdown"), ("values.json", "json")],
)
def test_kind_detection_by_mime_and_extension(project, name, kind):
    root, service = project
    (root / name).write_bytes(b"sample")
    assert service.metadata("workspace", name)["kind"] == kind


def test_zip_inventory_is_bounded_and_flags_traversal(project):
    root, service = project
    with zipfile.ZipFile(root / "bundle.zip", "w") as archive:
        archive.writestr("safe/a.txt", "a")
        archive.writestr("../escape.txt", "bad")
        archive.writestr("third.txt", "c")
    preview = service.preview("workspace", "bundle.zip", archive_limit=2)
    assert preview["format"] == "zip" and preview["total"] == 3
    assert preview["truncated"] is True
    assert preview["entries"][1]["unsafe_path"] is True


def test_tar_inventory_does_not_extract_and_flags_unsafe_links(project):
    root, service = project
    with tarfile.open(root / "bundle.tar", "w") as archive:
        payload = b"safe"
        member = tarfile.TarInfo("folder/file.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
        link = tarfile.TarInfo("link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)
    preview = service.preview("workspace", "bundle.tar")
    assert preview["format"] == "tar"
    assert preview["entries"][1] == {"name": "link", "type": "symlink", "size": 0, "unsafe_path": True}
    assert not (root / "folder").exists()


def test_large_binary_preview_uses_bounded_hex_ascii_fallback(project):
    root, service = project
    (root / "blob.bin").write_bytes(b"A\x00B" * 100)
    preview = service.preview("workspace", "blob.bin", max_bytes=6)
    assert preview["kind"] == "binary"
    assert preview["hex"] == "41 00 42 41 00 42"
    assert preview["ascii"] == "A.BA.B"
    assert preview["bytes"] == 6 and preview["truncated"] is True
