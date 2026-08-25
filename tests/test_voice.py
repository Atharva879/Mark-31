from __future__ import annotations

import pytest

from skills.voice import SpeechSynthesizer, VoiceInput


def test_voice_input_transcribes_one_bounded_in_memory_capture():
    seen: list[bytes] = []

    def transcribe(audio: bytes) -> str:
        seen.append(audio)
        assert audio == b"wav-data"
        return "  open   my   work apps  "

    voice = VoiceInput(
        max_seconds=3,
        recorder=lambda seconds, sample_rate: b"wav-data",
        transcriber=transcribe,
    )

    assert voice.listen_once() == "open my work apps"
    assert seen == [b"wav-data"]


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


def test_gemini_stt_sends_inline_audio_without_files(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "open calendar"}]}}]}

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr("skills.voice.requests.post", post)
    voice = VoiceInput(gemini_api_key="gemini-key", recorder=lambda *_: b"wav-data")

    assert voice.listen_once() == "open calendar"
    assert calls[0][1]["json"]["contents"][0]["parts"][1]["inline_data"]["data"]
    assert not any(Path for Path in [])


def test_gemini_tts_plays_decoded_audio_in_memory(monkeypatch):
    import base64
    import sys
    import types

    calls = []

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"output_audio": {"data": base64.b64encode(b"pcm-data").decode("ascii")}}

    monkeypatch.setattr("skills.voice.requests.post", lambda *args, **kwargs: Response())
    fake_numpy = types.SimpleNamespace(int16="int16", frombuffer=lambda data, dtype: (data, dtype))
    fake_sounddevice = types.SimpleNamespace(
        play=lambda pcm, samplerate, blocking: calls.append((pcm, samplerate, blocking)),
        stop=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "numpy", fake_numpy)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    speech = SpeechSynthesizer(gemini_api_key="gemini-key")
    speech._speak_gemini("hello")

    assert calls == [((b"pcm-data", "int16"), 24_000, True)]
