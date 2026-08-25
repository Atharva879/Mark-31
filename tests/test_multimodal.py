from __future__ import annotations

from pathlib import Path

import pytest

from skills.multimodal import MultimodalIngestor


def test_image_is_normalized_to_png_with_metadata(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    image_path = tmp_path / "sample.jpg"
    Image.new("RGB", (32, 18), (20, 40, 60)).save(image_path, format="JPEG")
    ingestor = MultimodalIngestor((tmp_path,))

    payload = ingestor.inspect_image(str(image_path))

    assert payload.width == 32
    assert payload.height == 18
    assert payload.source_mime_type == "image/jpeg"
    assert payload.png_bytes.startswith(b"\x89PNG")


def test_document_extraction_is_bounded_and_root_scoped(tmp_path: Path):
    document = tmp_path / "notes.md"
    document.write_text("Alpha\n\nBeta\n\nGamma", encoding="utf-8")
    ingestor = MultimodalIngestor((tmp_path,), max_chars=9)

    payload = ingestor.extract_document(str(document))

    assert payload.text == "Alpha Bet"
    assert payload.truncated is True

    with pytest.raises(PermissionError, match="outside"):
        ingestor.extract_document(str(tmp_path.parent / "outside.txt"))


def test_multimodal_rejects_unsupported_types(tmp_path: Path):
    file_path = tmp_path / "data.exe"
    file_path.write_bytes(b"not a document")
    ingestor = MultimodalIngestor((tmp_path,))

    with pytest.raises(ValueError, match="File type"):
        ingestor.extract_document(str(file_path))


def test_multimodal_requires_allowed_roots(tmp_path: Path):
    document = tmp_path / "notes.txt"
    document.write_text("hello", encoding="utf-8")
    ingestor = MultimodalIngestor(())

    with pytest.raises(PermissionError, match="JARVIS_ALLOWED_ROOTS"):
        ingestor.extract_document(str(document))
