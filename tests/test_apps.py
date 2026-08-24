from __future__ import annotations

from pathlib import Path

import pytest

from skills.apps import AppConfig, ApplicationController


def test_unknown_application_is_rejected(tmp_path):
    controller = ApplicationController(
        {"editor": AppConfig("Editor", tmp_path / "editor.exe")}
    )
    with pytest.raises(ValueError, match="not allowlisted"):
        controller.open("browser")


def test_application_control_fails_closed_outside_windows(tmp_path):
    controller = ApplicationController(
        {"editor": AppConfig("Editor", tmp_path / "editor.exe")}
    )
    with pytest.raises(RuntimeError, match="only on Windows"):
        controller.open("editor")
