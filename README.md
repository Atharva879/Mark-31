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
| Screen/scheduler integrations | Planned for later milestones |
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
