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
| Windows desktop integrations | Planned for later milestones |
| SimilarWeb analytics adapter | Planned for Milestone 10; credential/API boundary must be confirmed |

## Local setup

Use Python 3.11 or newer on the Windows computer that will eventually control desktop applications. Create and activate a virtual environment, install the base package and development extras, then copy `.env.example` to `.env` and add provider credentials locally.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

The first milestone does not require Windows-only dependencies because all registered tools are harmless mock tools. Install the Windows extras only when those integrations are being implemented:

```powershell
python -m pip install -e ".[providers,windows]"
```

Real `.env` files, audit logs, memory databases, virtual environments, and caches are excluded from version control. Never paste a provider key into source files, tests, issues, or commit messages.

## Configuration

`GEMINI_API_KEY` is used by the primary adapter, and `OPENROUTER_API_KEY` is used by the fallback adapter. `JARVIS_PROVIDER_ORDER` controls the order, defaulting to `gemini,openrouter`. Model names are configurable because free-tier availability can change. Runtime limits protect against large inputs and runaway tool loops.

The default CLI writes audit events to `logs/audit.jsonl`. It does not permanently delete files, send messages, submit forms, install software, or control desktop applications in Milestone 1.

## Run

```powershell
python main.py
```

Type `tools` to list the registered mock tools. Type a normal command to exercise the provider/tool loop, and type `exit` to quit. If the primary provider fails, the router retries according to configuration and then attempts the fallback provider with the same request. If no credentials are configured, the CLI reports a provider error rather than silently doing something else.

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
