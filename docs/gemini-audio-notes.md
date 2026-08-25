# Gemini Audio Integration Notes

Google’s official Gemini audio documentation says small audio can be passed inline as base64 audio data in an API request, with WAV among the supported formats, and asks the model for a transcript in the prompt. The audio guide is at https://ai.google.dev/gemini-api/docs/audio.

Google’s official speech-generation documentation says Gemini TTS uses audio response modality and current TTS model identifiers include `gemini-3.1-flash-tts-preview` and `gemini-2.5-flash-preview-tts`. The speech-generation guide is at https://ai.google.dev/gemini-api/docs/speech-generation.

Google’s official model catalog identifies `gemini-3.6-flash` as a stable general model, `gemini-3.1-flash-live-preview` as a preview low-latency voice model, and `gemini-3.1-flash-tts-preview` as a preview TTS model. It lists `gemini-2.0-flash` as shut down. The catalog is at https://ai.google.dev/gemini-api/docs/models.

Implementation boundary: capture microphone PCM/WAV bytes in memory, send them inline for transcription without writing a local audio file, and play TTS PCM returned by Gemini directly through an audio output stream without saving it. If an API path or audio device is unavailable, show a concise UI error and preserve typed/text operation.
