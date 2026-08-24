from __future__ import annotations

from pathlib import Path

import pytest

from skills.voice import SpeechSynthesizer, VoiceInput


def test_voice_input_transcribes_one_bounded_local_capture_and_cleans_temp_file():
    seen: list[Path] = []

    def transcribe(path: Path) -> str:
        seen.append(path)
        assert path.exists()
        assert path.read_bytes() == b"wav-data"
        return "  open   my   work apps  "

    voice = VoiceInput(
        max_seconds=3,
        recorder=lambda seconds, sample_rate: b"wav-data",
        transcriber=transcribe,
    )

    assert voice.listen_once() == "open my work apps"
    assert seen and not seen[0].exists()


def test_voice_input_rejects_invalid_duration():
    with pytest.raises(ValueError, match="between 0 and 60"):
        VoiceInput(max_seconds=0)
    with pytest.raises(ValueError, match="between 0 and 60"):
        VoiceInput(max_seconds=61)


class FakeEngine:
    def __init__(self):
        self.spoken: list[str] = []
        self.stopped = False

    def say(self, text: str) -> None:
        self.spoken.append(text)

    def runAndWait(self) -> None:
        return None

    def stop(self) -> None:
        self.stopped = True


def test_speech_synthesizer_runs_async_and_calls_completion():
    engine = FakeEngine()
    completed: list[bool] = []
    speech = SpeechSynthesizer(engine=engine)

    speech.speak_async("  Jarvis is ready. ", on_done=lambda: completed.append(True))
    speech._thread.join(timeout=2)

    assert engine.spoken == ["Jarvis is ready."]
    assert completed == [True]
    assert speech.speaking is False


def test_speech_synthesizer_stop_calls_engine_stop():
    engine = FakeEngine()
    speech = SpeechSynthesizer(engine=engine)
    speech.stop()
    assert engine.stopped is True
