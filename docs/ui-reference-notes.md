# UI Reference Notes

The supplied Jarvis reference video points toward a dark, high-tech HUD command center rather than a conventional business form. The implementation should preserve a restrained visual system: deep black or charcoal backgrounds, electric cyan as the primary accent, green for active/success states, red for thinking or recording states, and amber for warnings.

The observed composition is a three-zone desktop window. The left zone presents system telemetry and permission status. The center zone hosts the primary visualizer, using concentric rings and an audio-style waveform in the first implementation rather than requiring a 3D engine. The right zone presents conversation history and detailed output. Primary actions are minimal and context-driven, with large controls near the visualizer.

The observed interaction states are `LISTENING`, `THINKING`, and `SPEAKING`, with a visible interrupt action. The current UI implements those states for text-command execution and reserves voice capture and speech output for later milestones.

The observed settings pattern is an initialization or customization panel containing a Gemini API key and host configuration, with a color-customization concept. The current UI extends that pattern to both Gemini and OpenRouter fields, masks keys by default, permits temporary reveal, and allows provider order to be changed. Color customization is deferred until after the core UI is validated.

The video analysis could not identify the original UI framework with certainty. Tkinter and Canvas were selected for this first release because the application must remain a local Python desktop program and the core visual shell can run without a browser or hosted service.
