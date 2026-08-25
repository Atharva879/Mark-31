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

Voice input follows a push-to-talk lifecycle: `START VOICE` records one bounded utterance, writes a temporary WAV only for the local transcription step, deletes it in a `finally` block, and submits the normalized transcript through the ordinary dispatcher. Voice output uses a separate worker thread so the UI remains responsive; `INTERRUPT` calls the synthesizer stop hook and returns the visible state to `LISTENING`. Missing optional audio dependencies fail with a setup message rather than activating a different capture path.

Web retrieval is exposed through two safe tools. `web_search` queries DuckDuckGo’s public HTML search surface and falls back to the Instant Answer JSON endpoint for factual queries. `fetch_web_data` retrieves current text or JSON from a user- or model-specified public URL, but validates the scheme, resolves the host, blocks private/loopback/link-local/reserved/multicast addresses, enforces a byte cap, rejects binary content types, and never executes scripts. Both calls are bounded by a timeout and registered as `SAFE` because they read external data without changing the local system; their normalized outputs still pass through the dispatcher and audit logger.

Multimodal ingestion is local and root-scoped. `MultimodalIngestor` rejects paths outside `JARVIS_ALLOWED_ROOTS`, enforces a byte limit before parsing, validates image signatures with Pillow, normalizes accepted images to in-memory PNG bytes, extracts text from supported document formats, and caps extracted characters. The UI keeps image analysis on the Gemini vision adapter and routes document text through the normal provider failover path. The `/image` and `/document` commands are explicit; there is no background folder watcher or automatic upload pipeline.

The tool-calling boundary now includes `run_shell_command` and `browse_web_page`. Shell execution is never interpreted by a command shell: the executor tokenizes one command, checks the executable against `JARVIS_SHELL_ALLOWLIST`, blocks interpreter-evaluation and chaining arguments, constrains the working directory, and enforces timeout and output limits. It is `SENSITIVE`, requiring confirmation before execution. Browser navigation is read-only and delegates URL validation and content limits to `WebClient`; it cannot execute scripts, submit forms, start downloads, or control an interactive browser session.

Advanced file management adds recursive search, metadata, SHA-256 hashing, and archive-member inspection to the existing root-scoped file boundary. Archive inspection never extracts members and reports traversal-style names for review. Code execution is separate from shell execution: `CodeSandbox` parses Python with an AST policy, blocks imports, I/O, dynamic evaluation, classes, and dunder access, runs a short-lived isolated interpreter with no user site packages or stdin, and enforces timeout/output limits plus POSIX memory and file-size limits where supported. It is `SENSITIVE`; source code is hashed in audit records instead of being stored verbatim. This is an agent-safety sandbox, not a guarantee against a hostile local OS administrator.

Long-term memory composes the explicit SQLite `memories` table with a separate SQLite `memory_vectors` table. `HashEmbedding` provides deterministic offline feature-hash vectors, avoiding a network dependency or remote transmission of private memories. `LongTermMemory` updates both stores on writes, removes the vector on forget, supports bounded cosine-style similarity ranking, and can rebuild the vector index from the canonical SQLite records through the moderate-risk `reindex_memory` tool. The vector database is a derived index; the SQLite memory table remains the source of truth.

The desktop Memory Management panel uses the same `LongTermMemory` facade as the agent tools. It loads recent records asynchronously, supports semantic and lexical search, displays similarity and per-record vector presence, and refreshes after reindex or deletion. Deletion is a UI confirmation flow followed by a synchronized record/vector removal; the Tkinter event queue receives worker results so SQLite operations do not freeze the HUD.

Local model switching is provider-neutral at the router boundary. `Settings` validates model identifiers, accepts a unique fallback order from `local`, `gemini`, and `openrouter`, and rejects non-loopback local endpoints. `LocalLLMClient` reuses the OpenAI-compatible request translation against a localhost-only chat-completions endpoint, making it suitable for Ollama-style servers without sending keys or prompts to a remote endpoint. The settings panel writes the provider fields to the local `.env`, rebuilds the router, and preserves masked key presentation; failed provider requests continue through the configured order.

Multi-agent delegation is an explicit moderate-risk tool. `MultiAgentCoordinator` validates task IDs, role names, prompt lengths, subtask count, worker count, timeout, and aggregate result size. The fixed roles have narrow read-only tool scopes: research, memory, file inspection, and synthesis. Sensitive tools, delegation itself, and any state-changing operation are filtered from delegated tool lists; agents cannot recursively delegate. The coordinator runs bounded subtasks in a worker pool, returns per-task success/failure/timeout records, and emits start/completion/failure audit events. In the desktop app, moderate-risk notifications enter the Tkinter event queue rather than updating widgets from worker threads.

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
