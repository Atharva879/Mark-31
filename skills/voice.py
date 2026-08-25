"""In-memory Gemini voice input and output for the Jarvis desktop agent.

Microphone captures are bounded and held as bytes only. Production voice requires
Gemini credentials; injected recorder/transcriber/engine objects are retained for
unit tests and deterministic integrations without introducing local model fallbacks.
"""

from __future__ import annotations

import base64
import threading
from typing import Any, Callable

import requests


class VoiceInput:
    def __init__(
        self,
        model_size: str = "base",  # retained for backwards-compatible callers; never loads a model
        max_seconds: float = 10.0,
        sample_rate: int = 16_000,
        transcriber: Callable[[bytes], str] | None = None,
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

    def configure_gemini(self, api_key: str, model: str | None = None) -> None:
        self.gemini_api_key = api_key.strip()
        if model:
            self.gemini_model = model.strip() or self.gemini_model

    def listen_once(self) -> str:
        """Capture one bounded utterance and transcribe it without writing audio."""
        if self.audio_transcriber is None and not self.gemini_api_key and self.transcriber is None:
            raise RuntimeError("Gemini Voice requires a valid Gemini API key and model")
        audio_bytes = (
            self.recorder(self.max_seconds, self.sample_rate)
            if self.recorder
            else self._record_wav()
        )
        if not isinstance(audio_bytes, bytes) or not audio_bytes:
            raise RuntimeError("Voice recorder returned no audio")
        if self.audio_transcriber is not None:
            text = self.audio_transcriber(audio_bytes, "audio/wav")
        elif self.gemini_api_key:
            text = self._transcribe_gemini(audio_bytes)
        else:
            # Dependency injection only: production has no local transcription fallback.
            text = self.transcriber(audio_bytes)
        normalized = " ".join(str(text).split())
        if not normalized:
            raise RuntimeError("Voice transcription returned no spoken words")
        return normalized

    def _record_wav(self) -> bytes:
        try:
            import io
            import sounddevice as sd
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError(
                "Install sounddevice and soundfile for Gemini microphone capture"
            ) from exc
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
        engine: Any | None = None,  # test/integration injection only
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

    def configure_gemini(self, api_key: str, model: str | None = None) -> None:
        self.gemini_api_key = api_key.strip()
        if model:
            self.gemini_model = model.strip() or self.gemini_model

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
                elif self._engine is not None:
                    # Dependency injection only: no local TTS engine is created by production.
                    self._engine.say(text)
                    self._engine.runAndWait()
                else:
                    raise RuntimeError("Gemini Voice requires a valid Gemini API key and model")
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
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("Install numpy and sounddevice to play Gemini audio") from exc
        pcm = np.frombuffer(base64.b64decode(audio), dtype=np.int16)
        sd.play(pcm, samplerate=24_000, blocking=True)

    def stop(self) -> None:
        with self._lock:
            if self._engine is not None and hasattr(self._engine, "stop"):
                self._engine.stop()
            try:
                import sounddevice as sd

                sd.stop()
            except ImportError:
                pass
            self._speaking = False


__all__ = ["SpeechSynthesizer", "VoiceInput"]
