"""Local backup and recovery with explicit secret exclusion and integrity manifests."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


class BackupManager:
    def __init__(self, source_root: Path) -> None:
        self.source_root = Path(source_root).resolve()

    @staticmethod
    def _safe_relative(path: Path, root: Path) -> str:
        relative = path.resolve().relative_to(root)
        name = PurePosixPath(relative.as_posix())
        if (
            name.name == ".env"
            or name.name.endswith(".env")
            or any(part.startswith(".") and part == ".env" for part in name.parts)
        ):
            raise ValueError("environment files are excluded from backups")
        return name.as_posix()

    def create(self, destination: Path, files: list[Path]) -> Path:
        destination = Path(destination).resolve()
        entries: list[dict[str, object]] = []
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for raw in files:
                path = Path(raw).resolve()
                relative = self._safe_relative(path, self.source_root)
                if not path.is_file():
                    raise FileNotFoundError(path)
                data = path.read_bytes()
                archive.writestr(relative, data)
                entries.append(
                    {
                        "path": relative,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                    }
                )
            manifest = {"format": 1, "files": entries}
            archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True, indent=2))
        return destination

    @staticmethod
    def validate(archive_path: Path) -> dict[str, object]:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if "manifest.json" not in names:
                raise ValueError("backup manifest is missing")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != 1 or not isinstance(manifest.get("files"), list):
                raise ValueError("unsupported backup manifest")
            for entry in manifest["files"]:
                name = str(entry["path"])
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or name == ".env"
                    or name.endswith(".env")
                ):
                    raise ValueError("unsafe backup path")
                data = archive.read(name)
                if (
                    hashlib.sha256(data).hexdigest() != entry["sha256"]
                    or len(data) != entry["size"]
                ):
                    raise ValueError("backup checksum mismatch")
            return manifest

    def restore(self, archive_path: Path, target_root: Path) -> dict[str, object]:
        manifest = self.validate(archive_path)
        target = Path(target_root).resolve()
        with zipfile.ZipFile(archive_path) as archive:
            for entry in manifest["files"]:
                relative = PurePosixPath(str(entry["path"]))
                destination = (target / Path(*relative.parts)).resolve()
                destination.relative_to(target)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(str(relative)))
        return manifest


__all__ = ["BackupManager"]
