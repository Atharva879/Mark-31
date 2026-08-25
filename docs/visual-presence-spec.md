# Visual Presence Specification

## Purpose

Visual Presence lets Jarvis use screen or camera observations as optional context for proactive thoughts. It does not create continuous surveillance or an autonomous action channel. A visual source is completely disabled by default and can be activated only through an explicit user control or command.

## Permission model

| Source | Activation | Lifetime | Output |
|---|---|---|---|
| Screen | Existing explicit screen control | Bounded session with automatic expiry | In-memory PNG only unless the user explicitly requests analysis |
| Camera | New explicit camera control | Bounded session with automatic expiry | In-memory PNG only; no recording or video archive |

The HUD must show a distinct active indicator for each source. `STAY SILENT` prevents proactive visual capture and analysis. Disabling a source stops future captures immediately; a capture already in progress is allowed only to finish its bounded operation and is never persisted.

## Sampling and analysis

Visual Presence samples only while a source is explicitly active. It compares a bounded frame fingerprint before requesting vision analysis, so unchanged frames do not repeatedly reach a provider. Sampling and analysis are additionally subject to the existing Presence cooldown and limits. A proactive analysis may create a bounded event summary for Presence, but it cannot create a tool call or execute an action.

Cloud vision analysis is not implicit permission to upload private content. It requires an available configured vision provider and a visible active source indicator. If the provider is unavailable or analysis fails, Jarvis records a bounded failure status and remains silent rather than falling back to an unapproved destination. Raw frames, camera output, and provider prompts are not written to audit logs or disk.

## Camera privacy rules

Camera capture opens the device only for a bounded frame operation and releases it afterward. It must use a configured device index, reject unavailable devices, enforce a PNG size limit, and fail closed outside a supported desktop backend. The feature must not perform face recognition, identity inference, emotion diagnosis, biometric matching, hidden recording, or analysis of people for sensitive profiling.

## Proactive thought rules

A visual result is phrased as a short observation, such as “The active screen appears unchanged” or “I can see a document-like window.” It must not claim certainty beyond the provider output, invent personal facts, or tell the user that an unsafe action was completed. Visual observations are delivered through the ordinary activity queue and optional local TTS only; all system-changing actions remain behind the dispatcher and confirmation policy.

## Failure and lifecycle rules

The camera and screen controllers must be safe to use from worker threads, must not update Tkinter widgets directly, and must release device resources in `finally` blocks. The application must remain open for Visual Presence. Shutdown disables both sources, stops sampling, stops TTS, and closes any camera handle. The feature is tested with fake capture factories so the Linux development sandbox never needs a real camera or screen backend.
