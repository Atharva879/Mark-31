# Jarvis Agent

Jarvis Agent is a safety-first personal AI automation core designed to run locally on Windows. It accepts natural-language commands, asks a configured language model for a structured tool call, validates that call against a fixed registry, executes only the corresponding Python function, and records the outcome locally.

> **Important:** The language model is not an execution environment. Jarvis never evaluates model-generated Python, passes model-generated text to a shell, or grants the model unrestricted access to files, applications, or messages.

## Milestone 1 status

The repository currently contains the first vertical slice:

| Capability | Status |
|---|---|
| Gemini primary provider | Implemented through an isolated REST adapter |
| OpenRouter fallback provider | Implemented through an OpenAI-compatible REST adapter |
| Provider order and bounded retries | Implemented through environment configuration |
| Structured tool-call normalization | Implemented for both providers |
| Registry-based dispatcher | Implemented with argument validation |
| Risk tiers and sensitive confirmation hook | Implemented |
| Append-only JSONL audit log | Implemented with secret-like value redaction |
| Side-effect-free mock tools | Implemented |
| Persistent SQLite memory | Implemented with explicit remember, recall, and forget operations |
| Scoped file operations | Implemented with root enforcement, size limits, and Recycle Bin-only deletion |
| Windows application controls | Implemented as an allowlisted adapter; fails closed outside Windows |
| CLI diagnostics | Implemented |
| Discord messaging | Implemented as an optional allowlisted moderate-risk tool |
| WhatsApp Desktop messaging | Implemented as an optional dry-run-first UI Automation tool |
| Screen awareness | Implemented as opt-in, visible, time-limited Gemini vision support |
| Voice input and speech synthesis | Implemented as optional local push-to-talk voice support |
| Web search and real-time retrieval | Implemented with bounded DuckDuckGo search and safe public URL fetching |
| Image and document analysis | Implemented with scoped local ingestion and Gemini vision/text analysis |
| Agent shell and browser tools | Implemented with shell allowlists, confirmations, limits, and read-only web navigation |
| Advanced file management and code sandbox | Implemented with scoped search, metadata, hashing, archive inspection, and isolated pure-Python runs |
| Long-term vector memory | Implemented with a local SQLite vector index and offline deterministic embeddings |
| Memory Management panel | Implemented in the desktop UI for inspect, search, reindex, and confirmed deletion |
| Scheduler/clipboard integrations | Planned for later milestones |
| SimilarWeb analytics adapter | Planned for Milestone 10; credential/API boundary must be confirmed |

## Desktop interface

Running `python main.py` now opens the Jarvis desktop command center by default. The interface follows the supplied reference direction while keeping rendering clean: a dark HUD-style three-panel layout with restrained cyan accents, left-side system telemetry, a central animated circular visualizer, and a right-side activity feed. The UI presents `LISTENING`, `THINKING`, and `SPEAKING` states, includes an `INTERRUPT` control, uses readable Segoe UI/Cascadia Mono typography, and exposes diagnostics and permission status without requiring a terminal. Direct chat is no longer permanently embedded in the main window.

Use the `API CONFIG` button in the top-right panel to paste Gemini and OpenRouter keys directly into the application. The fields are masked by default, can be revealed temporarily, and save locally to `.env`; key values are not placed into chat history or audit records. `SAVE + APPLY` rebuilds the provider runtime without requiring a restart. The `PROVIDER ORDER` field controls failover order. Use `ENABLE CHAT MODE` beneath the HUD to open a separate chat window; `DISABLE CHAT MODE` closes it and returns the main window to activity-only mode.

The terminal mode remains available for diagnostics and automation-friendly use:

```powershell
python main.py --cli
```

## Local setup

Use Python 3.11 or newer on the Windows computer that will eventually control desktop applications. Create and activate a virtual environment, install the base package and development extras, then copy `.env.example` to `.env` and add provider credentials locally.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

WhatsApp Desktop automation is disabled by default. Set `WHATSAPP_ENABLED=true` to register the tool, but keep `WHATSAPP_DRY_RUN=true` while testing. Real sends require the user to set `WHATSAPP_DRY_RUN=false`, have WhatsApp Desktop already installed and logged in, and accept that the integration depends on UI selectors that may change.

Screen awareness is controlled by the `ENABLE SCREEN` button in the desktop UI. It is off by default, shows a red active indicator when enabled, and automatically expires after `JARVIS_SCREEN_TIMEOUT_SECONDS`. In Chat Mode, use `/screen <question>` to send one in-memory screenshot to Gemini vision. Screenshots are not written to disk by this milestone.

Voice input is activated explicitly with `START VOICE`. Each press records one bounded local utterance, transcribes it with `faster-whisper`, sends the resulting text through the same dispatcher and safety rules as typed commands, and then reads the response aloud with `pyttsx3`. Use `INTERRUPT` to stop speech output. Audio is not uploaded by the local adapters, and the microphone is not left listening continuously.

Web capabilities are available in Chat Mode and through the ordinary tool loop. Use `/search <query>` for bounded public DuckDuckGo results, or `/fetch <https-url>` to retrieve current text or JSON from a public endpoint. The fetcher enforces HTTP(S)-only URLs, blocks private and local network addresses, applies timeouts and response-size limits, rejects binary content types, and returns retrieval timestamps. It does not execute page scripts, follow arbitrary browser actions, or download files.

Multimodal analysis is available for files under `JARVIS_ALLOWED_ROOTS`. In Chat Mode, use `/image <path> | <question>` for PNG/JPEG/WebP/BMP/GIF image analysis or `/document <path> | <question>` for TXT/Markdown/CSV/JSON/XML/HTML/PDF/DOCX analysis. Images are validated and normalized to in-memory PNG bytes; documents are extracted locally, bounded, and then sent through provider-isolated Gemini vision or the normal provider failover path. The application does not execute document scripts or write uploaded copies to a separate staging directory.

Agent tool-calling now includes `run_shell_command` and `browse_web_page`. Shell execution accepts only configured executable names, never invokes a command shell, applies working-directory, argument, timeout, and output limits, and is classified as `SENSITIVE`, so the existing confirmation callback must approve every execution. Browser navigation is read-only and reuses the web safety boundary: no scripts, form submissions, downloads, or arbitrary interactive browser control. Use Chat Mode for natural-language tool selection, or use the explicit `/search` and `/fetch` commands for direct web retrieval.

Advanced file tools include `find_files`, `file_metadata`, `hash_file_sha256`, and `inspect_archive`. They remain rooted at `JARVIS_ALLOWED_ROOTS`; archive inspection only lists members and flags traversal-style names without extraction. `run_python_sandbox` executes small pure-Python calculations in a short-lived isolated subprocess, with AST restrictions, no imports or file/network APIs, a timeout, output cap, temporary working directory, and a POSIX memory/file-size limit. Sandbox execution is `SENSITIVE` and requires confirmation. Sandbox source is fingerprinted rather than written verbatim to audit logs.

Long-term memory stores the existing explicit notes and facts in SQLite and maintains a second local SQLite vector index in `JARVIS_VECTOR_DB`. The default embedding is deterministic and offline, so memory content is not sent to a remote embedding service. Use `semantic_recall_memory` for bounded similarity search and `reindex_memory` to rebuild the vector index if it is deleted or becomes inconsistent. Forgetting a memory removes both the record and its vector entry; the existing lexical `recall_memory` tool remains available.

The desktop UI now includes a `MEMORY` button that opens the Memory Management panel. It displays durable records, type, tags, similarity score, and per-record vector status; supports semantic or lexical search; allows explicit reindexing; and requires a confirmation dialog before deleting a selected memory. Operations run off the Tkinter event thread so the main HUD remains responsive.

The current build includes persistent memory and registers file tools when `JARVIS_ALLOWED_ROOTS` is configured. Application tools are always present but require an allowlist and a Windows host; they fail closed on other operating systems. The first milestone does not require Windows-only dependencies because the application adapter is not executable on the sandbox and file tools remain disabled until roots are configured. Install the Windows extras only when those integrations are being implemented:

```powershell
python -m pip install -e ".[providers,windows]"
```

Real `.env` files, audit logs, memory databases, virtual environments, and caches are excluded from version control. Never paste a provider key into source files, tests, issues, or commit messages.

## Configuration

`GEMINI_API_KEY` is used by the primary adapter, and `OPENROUTER_API_KEY` is used by the fallback adapter. `JARVIS_PROVIDER_ORDER` controls the order, defaulting to `gemini,openrouter`. Model names are configurable because free-tier availability can change. Runtime limits protect against large inputs and runaway tool loops.

The default CLI writes audit events to `logs/audit.jsonl` and stores explicit memories in `memory/memory.db`. File tools are disabled unless allowed roots are configured. It never permanently deletes files: the sensitive delete operation only moves a file to the operating system Recycle Bin. Application control accepts only configured allowlisted applications and is unavailable outside Windows.

## Run

```powershell
python main.py
```

Type a command in the right-side console to exercise the provider/tool loop. The terminal-only mode supports `tools`, `diagnostics`, normal commands, and `exit` through `python main.py --cli`. If the primary provider fails, the router retries according to configuration and then attempts the fallback provider with the same request. If no credentials are configured, the CLI reports a provider error rather than silently doing something else.

## Safety model

| Risk tier | Default behavior |
|---|---|
| `SAFE` | Execute automatically, while recording the action |
| `MODERATE` | Execute automatically with a visible notification and audit entry |
| `SENSITIVE` | Always require explicit confirmation; there is no global auto-approve mode |

Future file deletion will mean moving an item to the Windows Recycle Bin, never permanent deletion. Form submission, software installation, arbitrary scripts, payment-related operations, and other irreversible actions will remain sensitive even when triggered by a scheduled routine.

## Test

```powershell
python -m pytest
```

The tests use fake providers and harmless handlers. Network access and real desktop integrations are not required for the unit-test suite.

## Roadmap

The full implementation roadmap is captured in [`docs/architecture.md`](docs/architecture.md). The planned sequence is:

1. LLM router, schemas, dispatcher, audit, and mock tools.
2. Dedicated safety/configuration foundation.
3. Scoped Windows application and file operations.
4. SQLite memory.
5. Discord official bot integration.
6. WhatsApp Desktop UI Automation through `pywinauto`.
7. Opt-in screen awareness with visible capture status.
8. Scheduler, clipboard history, and declarative focus macros.
9. Web search and confirmation-gated form filling.
10. SimilarWeb website analytics.
11. Calendar, draft-only Gmail, and optional local voice I/O.

Each milestone should be implemented separately, tested with mocks before real actions are enabled, and reviewed for secret leakage and permission bypasses.
