"""Bounded, read-only filesystem projection for dashboard route adapters."""

from __future__ import annotations

import hashlib
import mimetypes
import re
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


DEFAULT_LIST_LIMIT = 100
MAX_LIST_LIMIT = 500
DEFAULT_PREVIEW_BYTES = 64 * 1024
MAX_PREVIEW_BYTES = 1024 * 1024
DEFAULT_ARCHIVE_LIMIT = 200
MAX_ARCHIVE_LIMIT = 1000

_CODE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".jsx", ".kt", ".lua", ".php", ".pl", ".py", ".rb",
    ".rs", ".sh", ".sql", ".swift", ".toml", ".ts", ".tsx", ".vue", ".xml",
    ".yaml", ".yml",
}
_TEXT_EXTENSIONS = {
    ".cfg", ".conf", ".csv", ".env", ".ini", ".log", ".properties", ".rst",
    ".text", ".txt",
}
_ARCHIVE_EXTENSIONS = {
    ".7z", ".bz2", ".gz", ".rar", ".tar", ".tbz", ".tbz2", ".tgz", ".xz", ".zip",
}


class PathSecurityError(ValueError):
    """Raised when a requested path could leave its registered project root."""


@dataclass(frozen=True)
class Project:
    id: str
    label: str
    root: Path

    def public(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


@dataclass(frozen=True)
class FileTarget:
    """A route-ready, validated local file target."""

    path: Path
    project_id: str
    relative_path: str
    name: str
    mime: str
    size: int


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "project"


def _bounded(value: int, *, default: int, maximum: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), maximum)


def _kind(path: Path, mime: str) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".json" or mime == "application/json":
        return "json"
    if suffix in {".md", ".markdown", ".mdown"}:
        return "markdown"
    if suffix in _CODE_EXTENSIONS:
        return "code"
    if mime.startswith("image/"):
        return "image"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    if suffix in _ARCHIVE_EXTENSIONS or mime in {
        "application/zip", "application/x-tar", "application/gzip", "application/x-bzip2", "application/x-xz",
    }:
        return "archive"
    if mime.startswith("text/") or suffix in _TEXT_EXTENSIONS:
        return "text"
    return "binary"


def _mime_and_kind(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(path.name, strict=False)[0] or "application/octet-stream"
    return mime, _kind(path, mime)


def _archive_path_unsafe(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    return (
        not normalized
        or normalized.startswith("/")
        or bool(re.match(r"^[a-zA-Z]:", normalized))
        or ".." in path.parts
    )


class FileService:
    """Read-only access to an explicit set of filesystem roots."""

    def __init__(self, roots: Mapping[str, Path] | Iterable[Path]):
        if isinstance(roots, Mapping):
            supplied = [(str(label), Path(path)) for label, path in roots.items()]
        else:
            supplied = [(Path(path).name or "Project", Path(path)) for path in roots]

        canonical: list[tuple[str, Path]] = []
        seen_roots: set[Path] = set()
        for label, root in supplied:
            resolved = root.expanduser().resolve(strict=True)
            if not resolved.is_dir():
                raise NotADirectoryError(resolved)
            if resolved in seen_roots:
                continue
            seen_roots.add(resolved)
            canonical.append((label.strip() or resolved.name or "Project", resolved))
        canonical.sort(key=lambda item: (item[0].casefold(), str(item[1])))

        projects: list[Project] = []
        used_ids: set[str] = set()
        for label, root in canonical:
            base = _slug(label)
            project_id = base
            if project_id in used_ids:
                digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:8]
                project_id = f"{base}-{digest}"
            used_ids.add(project_id)
            projects.append(Project(project_id, label, root))
        self._projects = tuple(projects)
        self._by_id = {project.id: project for project in projects}

    def projects(self) -> list[dict[str, str]]:
        """Return stable public IDs and labels without exposing server paths."""
        return [project.public() for project in self._projects]

    def _project(self, project_id: str) -> Project:
        try:
            return self._by_id[project_id]
        except KeyError as exc:
            raise KeyError(f"Unknown project: {project_id}") from exc

    @staticmethod
    def _contained(root: Path, candidate: Path) -> Path:
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(root):
            raise PathSecurityError("Path leaves the registered project root")
        return resolved

    def resolve(self, project_id: str, relative_path: str | Path = "") -> Path:
        """Resolve a project-relative path while rejecting traversal and symlink escape."""
        project = self._project(project_id)
        requested = Path(relative_path)
        if requested.is_absolute() or ".." in requested.parts:
            raise PathSecurityError("Only non-traversing project-relative paths are allowed")
        return self._contained(project.root, project.root / requested)

    def reference(self, path: str | Path, project_id: str | None = None) -> tuple[str, str]:
        """Return a normalized public project ID and project-relative path."""

        resolved_project_id, resolved = self.resolve_legacy(path, project_id)
        project = self._project(resolved_project_id)
        return resolved_project_id, self._relative(project, resolved)

    def resolve_legacy(self, path: str | Path, project_id: str | None = None) -> tuple[str, Path]:
        """Resolve old absolute, root-prefixed, or unambiguous relative path values."""
        requested = Path(path).expanduser()
        if ".." in requested.parts:
            raise PathSecurityError("Path traversal is not allowed")
        if project_id is not None:
            project = self._project(project_id)
            candidate = requested if requested.is_absolute() else project.root / requested
            return project.id, self._contained(project.root, candidate)

        matches: list[tuple[Project, Path]] = []
        for project in self._projects:
            if requested.is_absolute():
                candidate = requested
            elif requested.parts and requested.parts[0] in {project.id, project.root.name}:
                candidate = project.root.joinpath(*requested.parts[1:])
            else:
                candidate = project.root / requested
            try:
                resolved = self._contained(project.root, candidate)
            except PathSecurityError:
                continue
            if requested.is_absolute() or resolved.exists():
                matches.append((project, resolved))
        if not matches:
            raise PathSecurityError("Path is not under a registered project root")
        if requested.is_absolute() and len(matches) > 1:
            matches.sort(key=lambda item: len(item[0].root.parts), reverse=True)
            matches = matches[:1]
        if len(matches) > 1:
            raise PathSecurityError("Relative path is ambiguous across project roots")
        project, resolved = matches[0]
        return project.id, resolved

    def _relative(self, project: Project, path: Path) -> str:
        value = path.relative_to(project.root).as_posix()
        return "" if value == "." else value

    def list_directory(
        self,
        project_id: str,
        relative_path: str | Path = "",
        *,
        offset: int = 0,
        limit: int = DEFAULT_LIST_LIMIT,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        project = self._project(project_id)
        directory = self.resolve(project_id, relative_path)
        if not directory.exists():
            raise FileNotFoundError(directory)
        if not directory.is_dir():
            raise NotADirectoryError(directory)
        offset = max(int(offset), 0)
        limit = _bounded(limit, default=DEFAULT_LIST_LIMIT, maximum=MAX_LIST_LIMIT)
        entries: list[dict[str, Any]] = []
        for child in directory.iterdir():
            hidden = child.name.startswith(".")
            if hidden and not include_hidden:
                continue
            info = child.lstat()
            escaped = False
            if child.is_symlink():
                entry_type = "symlink"
                try:
                    self._contained(project.root, child)
                except PathSecurityError:
                    escaped = True
            elif child.is_dir():
                entry_type = "directory"
            else:
                entry_type = "file"
            item = {
                "name": child.name,
                "path": self._relative(project, child),
                "type": entry_type,
                "hidden": hidden,
                "size": info.st_size if entry_type != "directory" else None,
                "mtime": info.st_mtime,
            }
            if entry_type == "symlink":
                item["escaped"] = escaped
            entries.append(item)
        entries.sort(key=lambda item: (item["type"] != "directory", item["name"].casefold(), item["name"]))
        total = len(entries)
        page = entries[offset : offset + limit]
        return {
            "project_id": project.id,
            "path": self._relative(project, directory),
            "entries": page,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": offset + len(page) < total,
        }

    def metadata(self, project_id: str, relative_path: str | Path) -> dict[str, Any]:
        project = self._project(project_id)
        path = self.resolve(project_id, relative_path)
        if not path.exists():
            raise FileNotFoundError(path)
        info = path.stat()
        if path.is_dir():
            return {
                "project_id": project.id, "path": self._relative(project, path), "name": path.name,
                "type": "directory", "hidden": path.name.startswith("."), "size": None, "mtime": info.st_mtime,
                "mime": None, "kind": "directory",
            }
        mime, kind = _mime_and_kind(path)
        return {
            "project_id": project.id, "path": self._relative(project, path), "name": path.name,
            "type": "file", "hidden": path.name.startswith("."), "size": info.st_size, "mtime": info.st_mtime,
            "mime": mime, "kind": kind,
        }

    def target(self, project_id: str, relative_path: str | Path) -> FileTarget:
        """Return validated data suitable for raw or attachment response construction."""
        meta = self.metadata(project_id, relative_path)
        if meta["type"] != "file":
            raise IsADirectoryError(relative_path)
        path = self.resolve(project_id, relative_path)
        return FileTarget(path, project_id, meta["path"], meta["name"], meta["mime"], meta["size"])

    def preview(
        self,
        project_id: str,
        relative_path: str | Path,
        *,
        offset: int = 0,
        max_bytes: int = DEFAULT_PREVIEW_BYTES,
        archive_limit: int = DEFAULT_ARCHIVE_LIMIT,
    ) -> dict[str, Any]:
        target = self.target(project_id, relative_path)
        kind = _kind(target.path, target.mime)
        offset = max(int(offset), 0)
        max_bytes = _bounded(max_bytes, default=DEFAULT_PREVIEW_BYTES, maximum=MAX_PREVIEW_BYTES)
        base: dict[str, Any] = {
            "project_id": project_id, "path": target.relative_path, "mime": target.mime, "kind": kind,
            "size": target.size, "offset": offset,
        }
        if kind == "archive" and offset == 0:
            base.update(self._archive_inventory(target.path, archive_limit))
            return base

        with target.path.open("rb") as handle:
            handle.seek(min(offset, target.size))
            data = handle.read(max_bytes)
        end = min(offset, target.size) + len(data)
        base.update({"bytes": len(data), "next_offset": end, "truncated": end < target.size})
        if kind in {"text", "code", "json", "markdown"}:
            base["content"] = data.decode("utf-8", errors="replace")
            base["encoding"] = "utf-8"
        else:
            base["hex"] = " ".join(f"{byte:02x}" for byte in data)
            base["ascii"] = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in data)
        return base

    def _archive_inventory(self, path: Path, limit: int) -> dict[str, Any]:
        limit = _bounded(limit, default=DEFAULT_ARCHIVE_LIMIT, maximum=MAX_ARCHIVE_LIMIT)
        entries: list[dict[str, Any]] = []
        total = 0
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    total += 1
                    if len(entries) < limit:
                        entries.append({
                            "name": info.filename, "type": "directory" if info.is_dir() else "file",
                            "size": info.file_size, "compressed_size": info.compress_size,
                            "unsafe_path": _archive_path_unsafe(info.filename),
                        })
        elif tarfile.is_tarfile(path):
            with tarfile.open(path, mode="r:*") as archive:
                for info in archive:
                    total += 1
                    if len(entries) == limit:
                        break
                    unsafe = _archive_path_unsafe(info.name)
                    if info.issym() or info.islnk():
                        unsafe = unsafe or _archive_path_unsafe(info.linkname)
                    entries.append({
                        "name": info.name,
                        "type": "directory" if info.isdir() else "symlink" if info.issym() or info.islnk() else "file",
                        "size": info.size, "unsafe_path": unsafe,
                    })
        else:
            return {"format": "unsupported", "entries": [], "total": 0, "truncated": False}
        return {
            "format": "zip" if zipfile.is_zipfile(path) else "tar", "entries": entries,
            "total": total, "truncated": total > len(entries),
        }


def build_project_registry(roots: Mapping[str, Path] | Iterable[Path]) -> FileService:
    """Construct a filesystem service from app-supplied paths."""
    return FileService(roots)
