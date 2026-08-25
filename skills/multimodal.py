"""Safe local image and document ingestion for multimodal analysis."""

from __future__ import annotations

import io
import json
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree



IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}
DOCUMENT_SUFFIXES = TEXT_SUFFIXES | {".pdf", ".docx"}


@dataclass(frozen=True)
class ImagePayload:
    path: str
    png_bytes: bytes
    width: int
    height: int
    source_mime_type: str


@dataclass(frozen=True)
class DocumentPayload:
    path: str
    text: str
    mime_type: str
    truncated: bool


class MultimodalIngestor:
    def __init__(self, allowed_roots: tuple[Path, ...], max_bytes: int = 12_000_000, max_chars: int = 80_000) -> None:
        if max_bytes <= 0 or max_bytes > 50_000_000:
            raise ValueError("Multimodal byte limit must be between 1 and 50,000,000")
        if max_chars <= 0 or max_chars > 500_000:
            raise ValueError("Document character limit must be between 1 and 500,000")
        self.allowed_roots = tuple(root.expanduser().resolve() for root in allowed_roots)
        self.max_bytes = max_bytes
        self.max_chars = max_chars

    def inspect_image(self, path: str) -> ImagePayload:
        resolved = self._resolve_allowed(path, IMAGE_SUFFIXES)
        raw = self._read_bounded(resolved)
        source_mime = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Install the multimodal extras for image analysis") from exc
        try:
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                width, height = image.size
                if width * height > 40_000_000:
                    raise ValueError("Image dimensions exceed the safety limit")
                normalized = image.convert("RGBA")
                output = io.BytesIO()
                normalized.save(output, format="PNG", optimize=True)
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError("File is not a valid supported image") from exc
        png_bytes = output.getvalue()
        if len(png_bytes) > self.max_bytes:
            raise ValueError("Normalized image exceeds the safety size limit")
        return ImagePayload(str(resolved), png_bytes, width, height, source_mime)

    def extract_document(self, path: str) -> DocumentPayload:
        resolved = self._resolve_allowed(path, DOCUMENT_SUFFIXES)
        raw = self._read_bounded(resolved)
        suffix = resolved.suffix.lower()
        mime_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        if suffix in TEXT_SUFFIXES:
            text = raw.decode("utf-8", errors="replace")
        elif suffix == ".pdf":
            text = self._extract_pdf(resolved)
        elif suffix == ".docx":
            text = self._extract_docx(raw)
        else:  # pragma: no cover - guarded by suffix allowlist
            raise ValueError("Unsupported document type")
        cleaned = _clean_text(text)
        return DocumentPayload(str(resolved), cleaned[: self.max_chars], mime_type, len(cleaned) > self.max_chars)

    def _resolve_allowed(self, path: str, suffixes: set[str]) -> Path:
        if not isinstance(path, str) or not path.strip():
            raise ValueError("A local file path is required")
        if not self.allowed_roots:
            raise PermissionError("Configure JARVIS_ALLOWED_ROOTS before analyzing local files")
        candidate = Path(path).expanduser()
        resolved = candidate.resolve()
        if resolved.suffix.lower() not in suffixes:
            raise ValueError("File type is not enabled for multimodal analysis")
        if not any(resolved == root or root in resolved.parents for root in self.allowed_roots):
            raise PermissionError("File is outside the configured allowed roots")
        if not resolved.is_file():
            raise FileNotFoundError(str(resolved))
        return resolved

    def _read_bounded(self, path: Path) -> bytes:
        size = path.stat().st_size
        if size > self.max_bytes:
            raise ValueError("File exceeds the safety size limit")
        return path.read_bytes()

    @staticmethod
    def _extract_pdf(path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Install the multimodal extras for PDF analysis") from exc
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    @staticmethod
    def _extract_docx(raw: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                xml = archive.read("word/document.xml")
        except (KeyError, zipfile.BadZipFile) as exc:
            raise ValueError("File is not a valid DOCX document") from exc
        root = ElementTree.fromstring(xml)
        return " ".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))


def _clean_text(value: str) -> str:
    value = re.sub(r"\x00", "", value)
    return re.sub(r"\s+", " ", value).strip()


__all__ = ["DocumentPayload", "ImagePayload", "MultimodalIngestor"]
