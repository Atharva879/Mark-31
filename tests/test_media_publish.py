from pathlib import Path

import pytest

from media_publish import MediaPublisher


def test_latest_video_is_scoped_and_selects_newest(tmp_path: Path):
    older = tmp_path / "older.mp4"
    newer = tmp_path / "newer.mov"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    older.touch()
    newer.touch()
    older_time = older.stat().st_mtime
    import os

    os.utime(newer, (older_time + 10, older_time + 10))
    publisher = MediaPublisher([tmp_path])
    result = publisher.latest_video(str(tmp_path))
    assert result["name"] == "newer.mov"


def test_video_prepare_validates_provider_metadata_and_root(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")
    publisher = MediaPublisher([tmp_path])
    prepared = publisher.prepare("youtube", str(video), "My clip", "Description")
    assert prepared["publish_confirmation_required"] is True
    with pytest.raises(ValueError):
        publisher.prepare("linkedin", str(video), "title")
    with pytest.raises(ValueError):
        publisher.prepare("instagram", str(video), "")
    with pytest.raises(PermissionError):
        publisher.prepare("youtube", "/tmp/clip.mp4", "title")


def test_latest_video_rejects_unapproved_folder(tmp_path: Path):
    with pytest.raises(PermissionError):
        MediaPublisher([tmp_path]).latest_video(str(tmp_path.parent))
