"""Scoped filesystem tools for future dispatcher registration.

All operations resolve paths under explicitly configured roots. Deletion is
implemented as a Recycle Bin move only and is intended to remain SENSITIVE.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable


class ScopedFileManager:
    def __init__(self, allowed_roots: Iterable[Path], max_read_bytes: int = 1_000_000) -> None:
        roots = [Path(root).expanduser().resolve() for root in allowed_roots]
        if not roots:
            raise ValueError("At least one allowed root is required")
        self.allowed_roots = tuple(roots)
        self.max_read_bytes = max_read_bytes

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.allowed_roots[0] / candidate
        resolved = candidate.resolve(strict=False)
        if not any(_is_within(resolved, root) for root in self.allowed_roots):
            raise PermissionError(f"Path is outside configured roots: {path}")
        return resolved

    def list_files(self, directory: str | Path = ".", pattern: str = "*") -> list[str]:
        folder = self.resolve(directory)
        if not folder.is_dir():
            raise NotADirectoryError(str(folder))
        return sorted(
            str(item)
            for item in folder.iterdir()
            if item.is_file() and fnmatch.fnmatch(item.name, pattern)
        )

    def find_files(self, query: str = "*", directory: str | Path = ".", max_results: int = 100) -> list[str]:
        """Recursively find files by a bounded glob pattern under the configured roots."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("File search pattern cannot be empty")
        if max_results <= 0 or max_results > 1_000:
            raise ValueError("File search result limit must be between 1 and 1,000")
        folder = self.resolve(directory)
        if not folder.is_dir():
            raise NotADirectoryError(str(folder))
        return [str(item) for item in sorted(folder.rglob(query)) if item.is_file()][:max_results]

    def metadata(self, path: str | Path) -> dict[str, object]:
        target = self.resolve(path)
        if not target.exists():
            raise FileNotFoundError(str(target))
        stat = target.stat()
        return {
            "path": str(target),
            "name": target.name,
            "suffix": target.suffix.lower(),
            "is_file": target.is_file(),
            "is_directory": target.is_dir(),
            "size_bytes": stat.st_size,
            "modified_epoch": stat.st_mtime,
        }

    def sha256(self, path: str | Path, max_bytes: int = 100_000_000) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        if target.stat().st_size > max_bytes:
            raise ValueError("File exceeds the configured hashing limit")
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def inspect_archive(self, path: str | Path, max_entries: int = 200) -> dict[str, object]:
        """List archive members without extracting or executing archive contents."""
        target = self.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        if max_entries <= 0 or max_entries > 2_000:
            raise ValueError("Archive entry limit must be between 1 and 2,000")
        suffix = target.suffix.lower()
        if suffix == ".zip":
            with zipfile.ZipFile(target) as archive:
                members = archive.infolist()[:max_entries]
                entries = [{"name": item.filename, "size_bytes": item.file_size, "unsafe_path": _unsafe_member(item.filename)} for item in members]
                total = len(archive.infolist())
        elif suffix in {".tar", ".gz", ".tgz", ".bz2", ".xz"}:
            with tarfile.open(target) as archive:
                members = archive.getmembers()[:max_entries]
                entries = [{"name": item.name, "size_bytes": item.size, "unsafe_path": _unsafe_member(item.name)} for item in members]
                total = len(archive.getmembers())
        else:
            raise ValueError("Only ZIP and TAR-family archives are supported")
        return {"path": str(target), "entries": entries, "entry_count": total, "truncated": total > max_entries}

    def read_text(self, path: str | Path) -> str:
        target = self.resolve(path)
        if not target.is_file():
            raise FileNotFoundError(str(target))
        if target.stat().st_size > self.max_read_bytes:
            raise ValueError("File exceeds the configured read limit")
        raw = target.read_bytes()
        if b"\x00" in raw:
            raise ValueError("Binary files are not supported by read_text")
        return raw.decode("utf-8")

    def write_text(self, path: str | Path, content: str, overwrite: bool = False) -> str:
        target = self.resolve(path)
        if target.exists() and not overwrite:
            raise FileExistsError(str(target))
        if not isinstance(content, str) or len(content.encode("utf-8")) > self.max_read_bytes:
            raise ValueError("Content exceeds the configured write limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        return str(target)

    def move(self, source: str | Path, destination: str | Path) -> str:
        source_path = self.resolve(source)
        destination_path = self.resolve(destination)
        if not source_path.exists():
            raise FileNotFoundError(str(source_path))
        if destination_path.exists():
            raise FileExistsError(str(destination_path))
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(destination_path))
        return str(destination_path)

    def recycle(self, path: str | Path) -> str:
        """Move to the OS Recycle Bin; never permanently unlink a file."""
        target = self.resolve(path)
        if not target.exists():
            raise FileNotFoundError(str(target))
        try:
            from send2trash import send2trash
        except ImportError as exc:
            raise RuntimeError("send2trash is required for recycle-bin deletion") from exc
        send2trash(str(target))
        return str(target)


def _unsafe_member(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return normalized.startswith("/") or any(part == ".." for part in normalized.split("/"))


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = ["ScopedFileManager"]
