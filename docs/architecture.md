# Architecture and Security Notes

## System boundary

The local Windows process is the trusted execution boundary. The language model is an untrusted planner that may suggest a registered action, but it cannot directly access the operating system. Every request must cross the registry, schema validator, risk policy, and audit logger before a Python handler runs.

```text
User command
    |
    v
Context + bounded history
    |
    v
LLMRouter -- Gemini -> OpenRouter fallback
    |
    v
Normalized LLMResponse
    |
    v
ToolRegistry + JSON argument validation
    |
    v
Risk policy ---- SAFE: run
    |            MODERATE: notify + run
    |            SENSITIVE: explicit confirmation or stop
    v
Fixed Python handler
    |
    v
AuditLogger + tool result
    |
    v
Bounded follow-up loop -> final response
```

## Desktop UI

`ui.py` provides the default Python desktop application using Tkinter and Canvas, which keeps the first UI release dependency-light and Windows-friendly. Its three-panel composition follows the supplied reference: telemetry and permissions on the left, a central animated HUD, and the interaction console on the right. The visual state machine is `LISTENING -> THINKING -> SPEAKING -> LISTENING`; the interrupt control changes the visible state and records that active network calls cannot be cancelled retroactively.

The API configuration window contains masked Gemini and OpenRouter fields, a temporary reveal toggle, provider order, and `SAVE + APPLY`. Values are written only to the local `.env` file and applied to the in-memory settings. They are never inserted into chat messages or audit fields. A future release should replace or supplement `.env` persistence with the Windows Credential Manager for stronger at-rest secret handling.

The main window is activity-only by default. `ENABLE CHAT MODE` opens a separate, cleanly scaled chat window; `DISABLE CHAT MODE` closes it and returns to the activity feed. This keeps the HUD uncluttered while preserving an explicit interaction surface when the user wants direct conversation.

The Discord adapter is optional and becomes available only when a bot token and approved channel IDs are configured. It uses the official Discord HTTP API, limits messages to 2,000 characters, restricts destinations to the allowlist, and registers sends as `MODERATE` so the user receives visible notification and an audit record.

WhatsApp Desktop is an optional UI Automation adapter. It is disabled by default and remains dry-run by default even when enabled. In live mode it requires WhatsApp Desktop to be installed and already logged in, then searches for an explicit contact, selects the matching result, fills the message editor, and sends through the visible desktop application. Selector failures produce diagnostics instead of silently retrying another action. The action is `MODERATE` and is always audited by the dispatcher.

The repository’s first feature branch has now been merged into `main`. Future milestones should branch from the latest `origin/main` so the default GitHub view remains current.

Screen awareness is opt-in and separate from the normal tool loop. The UI must show `SCREEN ACTIVE` while capture is enabled, and `ScreenCapture` automatically expires the session after the configured timeout. A `/screen <question>` command captures one PNG in memory and sends it to the Gemini vision adapter; it does not write the image to disk or pass it through an unrelated provider. The capture backend rejects calls while disabled and caps payload size before encoding.

Voice input follows an explicit lifecycle: `START VOICE` records one bounded utterance as in-memory WAV bytes and submits inline audio to Gemini STT. It never writes a temporary audio file and never loads a local transcription model. Voice output uses a separate worker thread with Gemini TTS so the UI remains responsive; `INTERRUPT` calls the synthesizer stop hook and returns the visible state to `LISTENING`. Missing audio dependencies fail with a setup message rather than activating a local fallback.

Web retrieval is exposed through two safe tools. `web_search` queries DuckDuckGo’s public HTML search surface and falls back to the Instant Answer JSON endpoint for factual queries. `fetch_web_data` retrieves current text or JSON from a user- or model-specified public URL, but validates the scheme, resolves the host, blocks private/loopback/link-local/reserved/multicast addresses, enforces a byte cap, rejects binary content types, and never executes scripts. Both calls are bounded by a timeout and registered as `SAFE` because they read external data without changing the local system; their normalized outputs still pass through the dispatcher and audit logger.

Multimodal ingestion is local and root-scoped. `MultimodalIngestor` rejects paths outside `JARVIS_ALLOWED_ROOTS`, enforces a byte limit before parsing, validates image signatures with Pillow, normalizes accepted images to in-memory PNG bytes, extracts text from supported document formats, and caps extracted characters. The UI keeps image analysis on the Gemini vision adapter and routes document text through the normal provider failover path. The `/image` and `/document` commands are explicit; there is no background folder watcher or automatic upload pipeline.

The provider boundary contains only Gemini and OpenRouter. The tool-calling boundary now includes `run_shell_command` and `browse_web_page`. Shell execution is never interpreted by a command shell: the executor tokenizes one command, checks the executable against `JARVIS_SHELL_ALLOWLIST`, blocks interpreter-evaluation and chaining arguments, constrains the working directory, and enforces timeout and output limits. It is `SENSITIVE`, requiring confirmation before execution. Browser navigation is read-only and delegates URL validation and content limits to `WebClient`; it cannot execute scripts, submit forms, start downloads, or control an interactive browser session.

Advanced file management adds recursive search, metadata, SHA-256 hashing, and archive-member inspection to the existing root-scoped file boundary. Archive inspection never extracts members and reports traversal-style names for review. Code execution is separate from shell execution: `CodeSandbox` parses Python with an AST policy, blocks imports, I/O, dynamic evaluation, classes, and dunder access, runs a short-lived isolated interpreter with no user site packages or stdin, and enforces timeout/output limits plus POSIX memory and file-size limits where supported. It is `SENSITIVE`; source code is hashed in audit records instead of being stored verbatim. This is an agent-safety sandbox, not a guarantee against a hostile local OS administrator.

Long-term memory composes the explicit SQLite `memories` table with a separate SQLite `memory_vectors` table. `HashEmbedding` provides deterministic offline feature-hash vectors, avoiding a network dependency or remote transmission of private memories. `LongTermMemory` updates both stores on writes, removes the vector on forget, supports bounded cosine-style similarity ranking, and can rebuild the vector index from the canonical SQLite records through the moderate-risk `reindex_memory` tool. The vector database is a derived index; the SQLite memory table remains the source of truth.

The desktop Memory Management panel uses the same `LongTermMemory` facade as the agent tools. It loads recent records asynchronously, supports semantic and lexical search, displays similarity and per-record vector presence, and refreshes after reindex or deletion. Deletion is a UI confirmation flow followed by a synchronized record/vector removal; the Tkinter event queue receives worker results so SQLite operations do not freeze the HUD.

Provider routing is deliberately limited to Gemini and OpenRouter. `Settings` validates model identifiers and accepts a unique fallback order from those two providers only. The settings panel writes masked provider keys and model names to the local `.env`, rebuilds the router, refreshes Gemini voice credentials, and preserves the normal audit and safety boundaries when a provider fails.

Multi-agent delegation is an explicit moderate-risk tool. `MultiAgentCoordinator` validates task IDs, role names, prompt lengths, subtask count, worker count, timeout, and aggregate result size. The fixed roles have narrow read-only tool scopes: research, memory, file inspection, and synthesis. Sensitive tools, delegation itself, and any state-changing operation are filtered from delegated tool lists; agents cannot recursively delegate. The coordinator runs bounded subtasks in a worker pool, returns per-task success/failure/timeout records, and emits start/completion/failure audit events. In the desktop app, moderate-risk notifications enter the Tkinter event queue rather than updating widgets from worker threads.

### Monitoring and scheduled triggers

The scheduler is a local-process subsystem. `SchedulerStore` persists declarative trigger definitions and bounded run history in SQLite; `BackgroundScheduler` restores enabled definitions into APScheduler only after the desktop app starts and shuts down on app close. A schedule is not a Windows service, and missed work is coalesced rather than replayed without bound. The current trigger contract accepts only interval-based `reminder`, `web_url`, and `file` triggers, with a 60-second minimum and seven-day maximum interval. Reminders contain only bounded notification text; they cannot name a tool or action.

`MonitorRegistry` is deliberately read-only. Reminder callbacks only format a bounded local notification. Web monitors reuse `WebClient`, including HTTP(S)-only validation, DNS/IP SSRF blocking, timeout, content-type, response-size, and character caps. File monitors reuse `ScopedFileManager`, so every path resolves below `JARVIS_ALLOWED_ROOTS`; file fingerprints use bounded metadata or SHA-256. The first observation establishes a baseline, and notifications are emitted only for a detected fingerprint change or a failure. Monitor state is stored as bounded JSON in the trigger payload, while each attempt receives a run record with status and timestamps.

Schedule-management tools are registered with the ordinary dispatcher: listing/status are `SAFE`, create/pause/resume/run-now are `MODERATE`, and deletion is `SENSITIVE`. Scheduled monitors never contain arbitrary Python, shell text, browser actions, message destinations, or form submissions. If future scheduled routines invoke state-changing tools, they must create a new dispatcher request and preserve the existing moderate notification or sensitive confirmation gate; a background thread must never auto-approve a sensitive action. The UI reports scheduler readiness and routes worker results through the Tkinter event queue.

### Jarvis Presence

`PresenceEngine` is an output-only layer rather than another agent authority. `PresenceStore` persists enabled/silent state, the last user-activity timestamp, bounded proactive-message history, and bounded event summaries in a separate local SQLite database. The engine becomes eligible after 60 seconds of inactivity, but it chooses no message when the context is empty or limits have been reached. Defaults use a 10-minute ambient cooldown, two ambient messages per hour, 20 per local day, and recent-message fingerprints to avoid repetition.

Presence may read only the current time, recent Jarvis activity labels, bounded scheduler summaries, and local PresenceStore state. It does not capture the screen, listen to the microphone, inspect arbitrary files, call an LLM to manufacture chatter, or invoke a registered tool. Its candidate order prioritizes recent meaningful events, then scheduler awareness, then short local observations. Every emission is persisted before delivery, preventing duplicate output if multiple UI ticks overlap.

The HUD exposes `STAY SILENT` / `RESUME PRESENCE` and optional `VOICE PRESENCE ON/OFF`. Silence is persisted and checked before cooldowns, context, or speech; it therefore overrides both ambient and event-originated Presence output. Text output enters the existing Tkinter event queue, and optional speech uses the already local, user-controlled TTS adapter. Presence does not alter the dispatcher’s confirmation policy and cannot authorize an unattended action.

### Visual Presence

`CameraCapture` and `ScreenCapture` are separate explicit permission controllers. Each has a bounded session timeout, an active indicator, an in-memory PNG boundary, a maximum frame size, and a fail-closed backend check. Camera capture opens a device for a single frame and releases it in `finally`; it does not record video or persist images. The manual `/camera` command creates a temporary explicit camera session when needed and disables it after the bounded analysis.

`VisualObserver` samples only active sources and fingerprints each frame before analysis. Unchanged frames do not reach the vision provider, and changed-frame analysis is cooldown-limited. The observer serializes sampling per source, marks a frame as attempted before provider analysis so repeated failures cannot create a rapid retry loop, and returns only a truncated `VisualThought`. The UI passes that thought to `PresenceEngine.emit_observation`, so silence, cooldowns, daily/hourly limits, repetition protection, and audit metadata still apply.

The visual prompt requests broad, factual, non-sensitive observations and explicitly rejects identity recognition, emotion inference, credential reading, visible-instruction following, and action recommendations. Visual thoughts are output only. They cannot invoke tools, submit forms, send messages, execute code, or bypass sensitive confirmation. Raw frames and raw vision prompts are excluded from audit records; only bounded category, reason, and fingerprint metadata are written.

## Current implemented slice

The current branch includes a SQLite memory store, a scoped filesystem adapter, and an allowlisted application controller in addition to the original LLM router and dispatcher. Memory operations are explicit: notes and facts are written only through registered tools, recall is bounded, and forgetting a memory is sensitive. File operations require configured roots, enforce size limits, reject binary reads, and expose deletion only as a Recycle Bin move. Application control accepts configured executable paths only and fails closed on non-Windows hosts.

## Provider isolation

`llm/gemini_client.py` and `llm/openrouter_client.py` translate provider-specific HTTP payloads into the common `LLMResponse` model. `llm/router.py` does not inspect provider-specific response details. It tries providers in configured order and records route events for both successful and failed attempts.

A provider error never authorizes an alternative action. Fallback repeats the same logical request against the next configured provider. The router has a bounded retry count and a maximum tool-round limit.

## Tool registry contract

Each tool is defined by a `ToolSpec` containing a stable name, human-readable description, JSON-like parameter schema, Python handler, risk tier, and optional confirmation requirement. The dispatcher rejects unknown tool names, missing required arguments, unknown arguments when prohibited, wrong primitive types, oversized payloads, and unregistered execution paths.

Handlers must be small adapters around deterministic operations. A future handler may call a Windows API or a third-party client, but it must not accept a raw command string from the model and pass it to a shell. Complex routines should be declarative sequences of registered tools.

## Permission model

| Risk | Policy | Required implementation behavior |
|---|---|---|
| `SAFE` | Automatic | Validate, execute, audit |
| `MODERATE` | Automatic with visibility | Notify the user, execute, audit destination and payload metadata |
| `SENSITIVE` | Explicit confirmation | Show exact target and consequence, wait for confirmation, execute only when approved, audit the decision |

The confirmation callback is intentionally injected into the dispatcher. This keeps the policy testable and allows the CLI, a future tray application, or another UI to provide the confirmation surface without altering the execution rules. The current CLI uses a conservative default that denies sensitive actions until an interactive confirmation surface is wired in.

## Audit records

Audit entries are JSON objects written one per line. Each entry includes an event name and UTC timestamp, with request ID, tool name, risk tier, arguments, confirmation state, output, or error fields when available. Secret-like strings containing API-key or authorization markers are redacted before writing.

The audit log is not a security boundary by itself. File permissions and Windows account security remain important. Future releases should add retention controls and an option to encrypt or protect sensitive local logs.

## Threat model

### Prompt injection from retrieved content

Web pages and files are data, not instructions to the agent. A future search or file-summary skill must return content to the model in a clearly delimited context and must never treat embedded instructions as permission to call a new tool.

### Path traversal and overbroad file access

Future file tools must normalize paths, reject traversal outside configured roots, avoid following unexpected links where practical, enforce file-size limits, and use the Recycle Bin for deletion. The model must never choose an unrestricted filesystem root by default.

### Forged or ambiguous confirmations

Sensitive tools must display the concrete normalized arguments and consequence. A generic “yes” from an unrelated earlier message must not be reused as authorization. Confirmation state should be bound to a request ID and expire after the current action.

### Screen and clipboard disclosure

Screen capture and clipboard history can contain credentials and private communications. Screen awareness must be opt-in, visibly indicated, time-limited, and non-persistent by default. Clipboard retention must be bounded and disableable.

### Provider failure or compromise

Provider adapters must not expose secrets in logs or prompts. A provider’s refusal, malformed output, or outage must fail closed. Fallback changes only the provider, not the permission policy or tool registry.

### Fragile desktop UI automation

WhatsApp Desktop automation must verify the application window and intended contact as far as the accessibility tree permits. It should provide dry-run diagnostics and remain isolated behind an adapter so selector changes cannot affect core safety behavior.

## SimilarWeb integration contract

The planned SimilarWeb adapter will accept normalized domain names and monthly date ranges, enforce the permitted historical windows, cap country result counts, and immediately persist responses before formatting a report. Analytics are informational and cannot independently trigger an external action. Report delivery through messaging or email must create a separate dispatcher request with its own risk evaluation.

The Windows client must use a credentialed SimilarWeb API or an approved relay that is actually reachable from the local machine. It must not assume that a sandbox-only data interface is directly available on Windows.

## Delivery sequence

Milestone 1 is intentionally side-effect-free except for local audit writes. Later milestones should follow the same sequence: implement an adapter, add mocked tests, add a dry-run path where UI interaction is involved, add a real integration checklist, and only then register the action for normal use.
