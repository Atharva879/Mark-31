"""Optional local voice input and speech output adapters.

Voice input is bounded to a single push-to-talk capture. Speech output runs in a
worker thread and can be interrupted. No audio is uploaded by these adapters.
"""

from __future__ import annotations

import base64
import os
import tempfile
import threading
from pathlib import Path

import requests
from typing import Callable, Any


class VoiceInput:
    def __init__(
        self,
        model_size: str = "base",
        max_seconds: float = 10.0,
        sample_rate: int = 16_000,
        transcriber: Callable[[Path], str] | None = None,
        recorder: Callable[[float, int], bytes] | None = None,
        gemini_api_key: str = "",
        gemini_model: str = "gemini-3.7-flash",
        audio_transcriber: Callable[[bytes, str], str] | None = None,
    ) -> None:
        if max_seconds <= 0 or max_seconds > 60:
            raise ValueError("Voice capture must be between 0 and 60 seconds")
        self.model_size = model_size
        self.max_seconds = max_seconds
        self.sample_rate = sample_rate
        self.transcriber = transcriber
        self.recorder = recorder
        self.gemini_api_key = gemini_api_key.strip()
        self.gemini_model = gemini_model.strip() or "gemini-3.7-flash"
        self.audio_transcriber = audio_transcriber
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
            if self.audio_transcriber is not None or self.gemini_api_key:
                text = self._transcribe(None, audio_bytes)
            else:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                    path = Path(handle.name)
                    handle.write(audio_bytes)
                text = self._transcribe(path, audio_bytes)
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

    def _transcribe(self, path: Path | None, audio_bytes: bytes) -> str:
        if self.audio_transcriber is not None:
            return self.audio_transcriber(audio_bytes, "audio/wav")
        if self.gemini_api_key:
            return self._transcribe_gemini(audio_bytes)
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

    def _transcribe_gemini(self, audio_bytes: bytes) -> str:
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Transcribe this audio exactly. Return only the spoken words."},
                        {
                            "inline_data": {
                                "mime_type": "audio/wav",
                                "data": base64.b64encode(audio_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ]
        }
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent",
            params={"key": self.gemini_api_key},
            json=body,
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemini speech-to-text HTTP {response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
        parts = ((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        text = " ".join(str(part.get("text", "")) for part in parts).strip()
        if not text:
            raise RuntimeError("Gemini speech-to-text returned no transcript")
        return text


class SpeechSynthesizer:
    def __init__(
        self,
        rate: int = 175,
        engine: Any | None = None,
        gemini_api_key: str = "",
        gemini_model: str = "gemini-3.1-flash-tts-preview",
    ) -> None:
        self.rate = rate
        self._engine = engine
        self.gemini_api_key = gemini_api_key.strip()
        self.gemini_model = gemini_model.strip() or "gemini-3.1-flash-tts-preview"
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
                if self.gemini_api_key:
                    self._speak_gemini(text)
                else:
                    engine = self._get_engine()
                    engine.say(text)
                    engine.runAndWait()
            finally:
                self._speaking = False
                if on_done is not None:
                    on_done()

        self._thread = threading.Thread(target=worker, name="jarvis-tts", daemon=True)
        self._thread.start()

    def _speak_gemini(self, text: str) -> None:
        body = {
            "model": self.gemini_model,
            "input": text[:4000],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": "Kore"}]},
        }
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": self.gemini_api_key},
            json=body,
            timeout=30,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemini text-to-speech HTTP {response.status_code}: {response.text[:300]}"
            )
        audio = response.json().get("output_audio", {}).get("data")
        if not audio:
            raise RuntimeError("Gemini text-to-speech returned no audio")
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Install sounddevice to play Gemini audio") from exc
        pcm = base64.b64decode(audio)
        sd.play(pcm, samplerate=24_000, blocking=True)

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
