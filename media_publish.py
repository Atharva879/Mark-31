"""Local-first video publishing primitives for approved social destinations."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class VideoAsset:
    path: str
    name: str
    size_bytes: int
    modified_at: float
    mime_type: str


PROVIDER_CONFIG = {
    "youtube": {
        "url": "https://studio.youtube.com/",
        "file_selector": "input[type='file']",
        "title_selector": "input[aria-label*='Title'], input[placeholder*='title' i]",
        "description_selector": "textarea[aria-label*='Description'], textarea",
        "publish_selector": "button:has-text('Publish')",
    },
    "instagram": {
        "url": "https://www.instagram.com/",
        "file_selector": "input[type='file']",
        "title_selector": "textarea[aria-label*='caption' i], textarea",
        "description_selector": "textarea[aria-label*='caption' i], textarea",
        "publish_selector": "button:has-text('Share')",
    },
}


class MediaPublisher:
    def __init__(self, allowed_roots: list[Path], max_bytes: int = MAX_VIDEO_BYTES) -> None:
        self.allowed_roots = [Path(root).expanduser().resolve() for root in allowed_roots]
        self.max_bytes = max(1, min(int(max_bytes), MAX_VIDEO_BYTES))

    def _allowed(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        if not any(resolved == root or root in resolved.parents for root in self.allowed_roots):
            raise PermissionError("video path is outside configured allowed roots")
        if resolved.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError("unsupported video extension")
        if not resolved.is_file():
            raise FileNotFoundError(str(resolved))
        if resolved.stat().st_size > self.max_bytes:
            raise ValueError("video exceeds configured size limit")
        return resolved

    def latest_video(self, folder: str) -> dict[str, object]:
        root = Path(folder).expanduser().resolve()
        if not any(root == allowed or allowed in root.parents for allowed in self.allowed_roots):
            raise PermissionError("video folder is outside configured allowed roots")
        candidates = [
            self._allowed(path)
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if not candidates:
            raise FileNotFoundError("no supported video was found")
        path = max(candidates, key=lambda item: item.stat().st_mtime)
        stat = path.stat()
        return {
            "path": str(path),
            "name": path.name,
            "size_bytes": stat.st_size,
            "modified_at": stat.st_mtime,
            "mime_type": mimetypes.guess_type(path.name)[0] or "video/mp4",
        }

    def validate_provider(self, provider: str) -> str:
        value = str(provider).strip().lower()
        if value not in {"youtube", "instagram"}:
            raise ValueError("provider must be youtube or instagram")
        return value

    def browser_prepare(
        self, provider: str, asset_path: str, title: str, description: str, browser
    ) -> dict[str, object]:
        plan = self.prepare(provider, asset_path, title, description)
        config = PROVIDER_CONFIG[plan["provider"]]
        browser.navigate(config["url"])
        browser.upload_file(config["file_selector"], plan["path"])
        if plan["provider"] == "youtube":
            browser.fill(config["title_selector"], plan["title"])
            if plan["description"]:
                browser.fill(config["description_selector"], plan["description"])
        else:
            caption = plan["title"] + ("\n\n" + plan["description"] if plan["description"] else "")
            browser.fill(config["description_selector"], caption[:2000])
        return {
            **plan,
            "status": "ready_for_review",
            "publish_selector": config["publish_selector"],
        }

    def browser_publish(self, provider: str, browser) -> dict[str, object]:
        provider = self.validate_provider(provider)
        selector = PROVIDER_CONFIG[provider]["publish_selector"]
        browser.click(selector)
        return {"provider": provider, "status": "publish_requested", "confirmation_required": True}

    def prepare(
        self, provider: str, asset_path: str, title: str, description: str = ""
    ) -> dict[str, object]:
        provider = self.validate_provider(provider)
        path = self._allowed(Path(asset_path))
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("title must be non-empty and under 200 characters")
        if not isinstance(description, str) or len(description) > 5_000:
            raise ValueError("description is too long")
        return {
            "provider": provider,
            "path": str(path),
            "name": path.name,
            "title": title.strip(),
            "description": description[:5_000],
            "publish_confirmation_required": True,
        }


__all__ = ["MAX_VIDEO_BYTES", "MediaPublisher", "VideoAsset"]
