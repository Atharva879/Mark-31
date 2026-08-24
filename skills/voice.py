"""Optional local voice input and speech output adapters.

Voice input is bounded to a single push-to-talk capture. Speech output runs in a
worker thread and can be interrupted. No audio is uploaded by these adapters.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Any


class VoiceInput:
    def __init__(
        self,
        model_size: str = "base",
        max_seconds: float = 10.0,
        sample_rate: int = 16_000,
        transcriber: Callable[[Path], str] | None = None,
        recorder: Callable[[float, int], bytes] | None = None,
    ) -> None:
        if max_seconds <= 0 or max_seconds > 60:
            raise ValueError("Voice capture must be between 0 and 60 seconds")
        self.model_size = model_size
        self.max_seconds = max_seconds
        self.sample_rate = sample_rate
        self.transcriber = transcriber
        self.recorder = recorder
        self._model: Any = None

    def listen_once(self) -> str:
        """Record one bounded utterance and return normalized text."""
        if self.recorder is not None:
            audio_bytes = self.recorder(self.max_seconds, self.sample_rate)
            if not isinstance(audio_bytes, bytes) or not audio_bytes:
                raise RuntimeError("Voice recorder returned no audio")
        else:
            audio_bytes = self._record_wav()

        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                path = Path(handle.name)
                handle.write(audio_bytes)
            text = self._transcribe(path)
            return " ".join(text.split())
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _record_wav(self) -> bytes:
        try:
            import sounddevice as sd
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("Install the voice extras for microphone capture") from exc
        import io

        recording = sd.rec(
            int(self.max_seconds * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        buffer = io.BytesIO()
        sf.write(buffer, recording, self.sample_rate, format="WAV")
        return buffer.getvalue()

    def _transcribe(self, path: Path) -> str:
        if self.transcriber is not None:
            return self.transcriber(path)
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("Install the voice extras for local transcription") from exc
            device = os.environ.get("JARVIS_WHISPER_DEVICE", "cpu")
            compute_type = os.environ.get("JARVIS_WHISPER_COMPUTE_TYPE", "int8")
            self._model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
        segments, _info = self._model.transcribe(str(path), beam_size=1, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()


class SpeechSynthesizer:
    def __init__(self, rate: int = 175, engine: Any | None = None) -> None:
        self.rate = rate
        self._engine = engine
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._speaking = False

    @property
    def speaking(self) -> bool:
        return self._speaking

    def speak_async(self, text: str, on_done: Callable[[], None] | None = None) -> None:
        text = " ".join(text.split())
        if not text:
            return
        self.stop()
        self._speaking = True

        def worker() -> None:
            try:
                engine = self._get_engine()
                engine.say(text)
                engine.runAndWait()
            finally:
                self._speaking = False
                if on_done is not None:
                    on_done()

        self._thread = threading.Thread(target=worker, name="jarvis-tts", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if self._engine is not None and hasattr(self._engine, "stop"):
                self._engine.stop()
            self._speaking = False

    def _get_engine(self) -> Any:
        if self._engine is None:
            try:
                import pyttsx3
            except ImportError as exc:
                raise RuntimeError("Install the voice extras for speech synthesis") from exc
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self.rate)
        return self._engine


__all__ = ["SpeechSynthesizer", "VoiceInput"]
