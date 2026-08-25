# Jarvis-Style Personal AI Automation Agent — Implementation Plan

## Goal

Build a Python 3.11+ personal AI automation agent for **Windows** in the selected GitHub repository **`Atharva879/Mark-31`**. The agent will understand natural-language commands, convert them into validated structured tool calls, execute only fixed Python functions, return results to the language model for follow-up reasoning, and enforce explicit safety boundaries for irreversible actions.

The implementation will begin with **Milestone 1: the dual-provider LLM router and a basic tool-calling loop**, then proceed through the complete roadmap in controlled, testable increments. The `/similarweb-analytics` request will be treated as a requirement to include a SimilarWeb-based website analytics capability in the roadmap, subject to credentials/API availability.

## Current Environment and Constraints

The sandbox contains the supplied brief but no local checkout of `Atharva879/Mark-31`; the implementation phase must clone and inspect the repository before changing it. Plan Mode does not modify the repository or external services.

The target runtime is the user’s own Windows computer, not a hosted Linux service. This is necessary for desktop control, `pywin32`, `pyautogui`, Windows UI Automation, WhatsApp Desktop, screenshots, and local user data. The agent should be developed so that core logic remains testable on other operating systems, while Windows-only adapters fail clearly when unavailable.

The agent must never allow the LLM to execute arbitrary shell commands, generated Python, unrestricted file operations, unconfirmed destructive actions, or unreviewed irreversible submissions.

## Architecture Decision

The primary product will be a **local Windows command-line application**, with an extensible adapter architecture. The LLM layer will expose one provider-independent interface. Gemini will be the default provider, and OpenRouter will be the automatic fallback for request errors, timeouts, and rate limits. Provider selection, retry behavior, timeouts, model names, and logging will be configuration-driven through `.env` and typed application settings.

The central execution path will be:

1. Accept a natural-language command from the terminal and, later, optional voice input.
2. Load relevant memory and current session context.
3. Send the command plus a strict tool schema to the configured LLM provider.
4. Parse and validate the structured response against registered tool definitions.
5. Classify the requested action as `SAFE`, `MODERATE`, or `SENSITIVE`.
6. Auto-execute safe tools; execute moderate tools with an audit entry and user-visible notification; stop for explicit confirmation before sensitive tools.
7. Execute only the registered Python function, never arbitrary model-generated code.
8. Feed the tool result back into the LLM for a concise user-facing response or another validated tool call.
9. Record the request, provider, tool, risk tier, confirmation state, result status, and errors in the local audit log.

A registry-based dispatcher will keep tool metadata together: tool name, JSON input schema, Python callable, risk tier, allowed path/scope rules, confirmation policy, and user-facing description. This will make new skills additive rather than requiring changes throughout the command loop.

## Repository and Project Layout

During implementation, the repository will be inspected first and existing conventions will be preserved. If the repository is empty or unrelated, the following structure will be introduced:

```text
jarvis-agent/
├── main.py
├── config.py
├── pyproject.toml
├── requirements.txt or uv.lock
├── .env.example
├── README.md
├── llm/
│   ├── __init__.py
│   ├── router.py
│   ├── gemini_client.py
│   ├── openrouter_client.py
│   └── schemas.py
├── skills/
│   ├── __init__.py
│   ├── apps.py
│   ├── files.py
│   ├── messaging_whatsapp.py
│   ├── messaging_discord.py
│   ├── screen.py
│   ├── forms.py
│   ├── system_control.py
│   ├── clipboard.py
│   ├── scheduler.py
│   ├── web_search.py
│   └── similarweb.py
├── memory/
│   ├── __init__.py
│   └── store.py
├── dispatcher.py
├── safety.py
├── audit.py
├── logs/
├── tests/
│   ├── test_router.py
│   ├── test_dispatcher.py
│   ├── test_safety.py
│   ├── test_memory.py
│   └── fixtures/
└── docs/
    └── architecture.md
```

The exact layout will be adjusted if the selected repository already has an established Python package structure.

## Milestone 1 — LLM Router and Tool-Calling Loop

### Implementation scope

Create a minimal but production-shaped vertical slice with no real desktop side effects initially.

The router will provide a shared interface for:

- Gemini as the primary provider using the current supported Google client/API approach.
- OpenRouter through its OpenAI-compatible chat-completions interface as the fallback.
- Per-request timeout, bounded retry, provider failure classification, and structured logging.
- A configurable provider order so the user can swap primary and fallback without code changes.
- Strict tool/function schemas and normalized provider responses.
- A clear error when neither provider succeeds.

The initial tool loop will include harmless mock tools such as `get_current_time`, `remember_note`, or `echo_status`, allowing the full routing and dispatch path to be exercised without touching files, applications, messages, or the operating system.

The dispatcher will validate tool names and arguments, reject unknown fields where practical, enforce maximum payload sizes, and prevent the model from bypassing the registry. Confirmation handling will be represented in the interface from the first milestone even if only safe mock tools are enabled.

### Configuration

Add an `.env.example` containing placeholders for Gemini and OpenRouter credentials, model names, request timeouts, retry limits, log level, allowed Windows roots, and feature flags. Real credentials will never be committed. The README will document environment setup, installation, running the CLI, and provider fallback behavior.

### Tests and acceptance criteria

Milestone 1 is complete when:

- A normal request is answered through the primary provider.
- A simulated primary timeout, rate limit, or server error routes the same request to the fallback provider and records the switch.
- Malformed model output, unknown tools, invalid arguments, and oversized inputs are rejected safely.
- A multi-turn tool result loop works using mocked providers without external network calls.
- No arbitrary shell/code execution path exists in the dispatcher.
- Sensitive tool calls cannot execute without an explicit confirmation callback.
- Unit tests cover provider selection, fallback, parsing, validation, dispatcher routing, and failure handling.
- Secrets are excluded by `.gitignore`, and a repository scan confirms that no credential values are committed.

## Milestone 2 — Safety, Audit, and Configuration Foundation

Implement a dedicated safety layer and local audit logger before enabling real actions. Define the three risk tiers precisely:

| Tier | Default behavior | Examples |
|---|---|---|
| `SAFE` | Execute automatically | Read approved text files, open an application, search the web, capture a requested screenshot |
| `MODERATE` | Execute automatically with visible notification and audit record | Send WhatsApp/Discord messages, create or move files, read clipboard history |
| `SENSITIVE` | Always pause for explicit confirmation | Delete/recycle files, submit forms, install software, run scripts, payment-related actions |

Sensitive actions will have no global auto-approve mode. Confirmation prompts will show the exact action, target, relevant parameters, and potential consequence. The audit log will be append-only from the application’s perspective and include timestamps, session IDs, provider, requested command, normalized tool call, risk tier, confirmation result, execution result, and error details.

## Milestone 3 — Application and File Operations

Add Windows application control for opening, focusing, and closing named applications using a curated allowlist and safe process APIs. Add scoped file operations restricted by default to Desktop, Documents, and Downloads. Implement create, read, summarize, search, move, rename, and organize operations with path normalization and traversal protection.

Deletion will never be permanent. The only supported delete behavior will move files to the Windows Recycle Bin, require sensitive confirmation, and log the original path and outcome. File reads will enforce size limits and text/binary detection to prevent accidental ingestion of large or sensitive content.

## Milestone 4 — Local Memory

Implement SQLite-backed memory with explicit commands such as “remember X,” “forget X,” and “what do you remember about Y.” Separate durable key-value facts from freeform notes. Add timestamps, source, optional tags, and deletion/forget semantics. Only relevant, bounded memory results should be injected into an LLM request, with controls to avoid leaking unrelated local data.

Tests will use temporary SQLite databases and verify persistence, recall relevance filtering, update behavior, and isolation between test sessions.

## Milestone 5 — Discord Integration

Implement Discord through the official bot API rather than desktop UI automation. Store the bot token only in environment configuration. Restrict sends to configured guilds/channels or approved recipients. Treat sends as `MODERATE`: automatically execute, visibly notify the user, and record the exact destination and message in the audit log.

Add mocked API tests for successful sends, invalid destinations, API failures, rate limits, and audit behavior. Real integration testing will require the user to provide/configure a Discord bot and permitted destination.

## Milestone 6 — WhatsApp Desktop Integration

Implement WhatsApp Desktop automation through Windows UI Automation using `pywinauto` with the UIA backend. Require WhatsApp Desktop to be installed and already logged in by the user. Build selectors behind a small adapter layer so UI changes can be fixed without changing the dispatcher.

The workflow will locate the WhatsApp window, search for an explicitly named contact, focus the message box, type the message safely, and send it. It will verify the intended contact and message content before sending as far as the accessibility tree permits. Sends remain `MODERATE`, with visible notification and audit logging. The implementation will include a dry-run mode and diagnostics for missing windows/selectors.

Because this is the most fragile integration, the milestone will include a documented manual test matrix across window states, contact names with special characters, unavailable contacts, multiple search results, reconnects, and WhatsApp UI updates.

## Milestone 7 — Screen Awareness

Add on-demand screenshot capture through `mss` and optional Gemini vision analysis. Screen sharing will be explicitly opt-in, visibly indicated through a tray/overlay status, limited to a configurable timeout, and automatically disabled after the timeout or command completion. Screenshots will not be stored permanently by default.

The safety layer will treat screenshots as potentially sensitive data. The user-facing status will state when capture is active and what is being sent for analysis. Tests will mock capture and vision calls, confirm timeout behavior, and verify that screen capture cannot silently remain active.

## Milestone 8 — Scheduler, Clipboard, and Context Macros

Add APScheduler-based reminders and recurring routines for actions such as opening work applications. Recurring routines will reuse the same dispatcher and permission checks; scheduling a sensitive action will not bypass confirmation. Persist schedules locally and provide list, pause, resume, and remove commands.

Add a bounded clipboard history using Windows clipboard access, with configurable retention, size limits, and opt-out behavior. Clipboard reads remain `MODERATE` because they may expose private information.

Add named context macros, such as a focus routine that closes selected distracting applications, mutes notifications where supported, and opens configured work applications. Each macro will be a declarative sequence of registered tools rather than arbitrary code.

## Milestone 9 — Form Filling and Web Search

Add web search/info retrieval through a configured search provider or another explicitly selected API. Search results will be treated as untrusted data; webpage instructions will never be executed merely because they appear in retrieved content.

Implement form filling with Playwright for web forms and `pyautogui`/`pyperclip` for desktop forms where appropriate. The agent may detect and fill fields from approved profile data, but it must pause before final submission unless the exact action is explicitly whitelisted. Payment, account changes, purchases, and other irreversible submissions always require sensitive confirmation.

## Milestone 10 — SimilarWeb Analytics

Add a dedicated `skills/similarweb.py` adapter that exposes structured website analytics commands, such as:

- Total monthly visits.
- Unique visits.
- Bounce rate.
- Global ranking.
- Desktop and mobile traffic-source breakdowns.
- Traffic by country.
- Domain comparison, using repeated normalized queries and a consistent date range.

The adapter will enforce SimilarWeb data constraints: monthly granularity, historical windows no longer than 12 months, and the shorter maximum range for country data. The latest period will default to the most recent complete month. It will normalize domains, validate date ranges, cap country result limits, and save retrieved responses immediately to local data files or a SQLite cache to reduce redundant API calls and protect against mid-run failures.

The implementation path depends on how the local Windows application will access SimilarWeb data. The preferred design is a user-supplied SimilarWeb API credential or approved API proxy configured in `.env`; if the available SimilarWeb capability is only accessible through the Manus environment, the plan will instead define an export/import boundary or a small authenticated relay rather than embedding inaccessible sandbox-only assumptions in the Windows client.

SimilarWeb results are informational and should not cause actions automatically. Any downstream action based on analytics, such as sending a report or changing a workflow, must pass through the normal dispatcher and risk tiers.

## Milestone 11 — Calendar, Email, and Voice Polish

Add Google Calendar and Gmail only after the core safety model is stable. Gmail integration will be draft-only by default and will never auto-send. Calendar creation or modification will show the exact event details before confirmation when appropriate.

Add bounded Gemini STT/TTS voice through in-memory audio payloads. Voice input will feed the same text command pipeline and will not receive weaker safety rules. Include push-to-talk or explicit normal-talk activation to avoid unintended capture; do not persist microphone audio or ship a local speech model.

## User Experience

The initial interface will be a clear terminal command loop with readable status messages for provider selection, tool execution, confirmations, and errors. The CLI will offer commands to inspect available tools, view recent audit entries, list schedules, toggle screen awareness, and run diagnostics.

Later, the project may add a Windows tray interface, but this is not required for the first implementation. The code should keep UI concerns separate from the dispatcher so a tray or local web dashboard can be added without weakening the permission model.

## Testing Strategy

Testing will be layered:

| Layer | Coverage | Approach |
|---|---|---|
| Unit | Routing, schemas, safety tiers, path rules, memory, date validation | Pure Python tests with mocked providers and temporary directories/databases |
| Integration | Provider clients, SimilarWeb adapter, Discord adapter, scheduler persistence | Mock HTTP/API fixtures plus opt-in credentialed tests |
| Windows integration | App control, clipboard, screenshots, Recycle Bin, WhatsApp UIA, desktop forms | Dedicated Windows test checklist, dry-run modes, and manual verification |
| End-to-end | Natural language to validated tool call to audited result | Fake LLM responses and harmless test tools first; real actions only in a user-controlled environment |
| Security/regression | Prompt injection, path traversal, arbitrary tool names, forged confirmations, secret leakage | Adversarial fixtures and repository secret scanning |

CI should run platform-independent tests on every change. Windows-specific tests should be marked separately and run on a Windows runner or manually during integration milestones. Network-dependent tests must never be required for ordinary unit-test success.

## Documentation and Operational Requirements

The README will document installation, Python version, virtual environment setup, Windows permissions, environment variables, provider selection, initial diagnostics, safety behavior, and troubleshooting. Include a setup checklist for Gemini, OpenRouter, Discord, WhatsApp Desktop, SimilarWeb access, Google APIs, and optional voice dependencies.

Provide an explicit threat model covering prompt injection from web pages/files, accidental disclosure through screenshots/clipboard, malicious or malformed tool calls, path traversal, provider compromise/failure, and UI automation drift.

Include a migration note for provider model names because free-tier model availability can change. Provider errors and fallback decisions must remain observable without exposing secret values.

## Viable Execution Options

| Approach | Tradeoffs | Cost | Setup Complexity |
|---|---|---|---|
| Run the complete agent locally on the user’s Windows PC | Best access to Windows apps, WhatsApp Desktop, clipboard, screen, and local files; the computer must be online and the user must install/configure dependencies | No additional hosting cost; provider/API usage may apply | Medium to high |
| Develop on GitHub and run the agent locally through a packaged Windows setup | Reproducible source control and releases; still requires local installation and user-side credentials; desktop integrations remain local | No additional hosting cost; packaging/release maintenance required | High initially, lower for updates |
| Build only a lightweight command-line core with mock tools first | Fastest and safest starting point; does not yet control apps, send messages, or provide screen awareness | Lowest | Low |

The recommended sequence is to implement the lightweight core first, then run the full desktop agent locally. A hosted web application is not the primary route because it cannot directly and reliably control the user’s Windows desktop or WhatsApp Desktop session.

## GitHub Workflow for Implementation

After approval, the implementation phase will:

1. Clone `Atharva879/Mark-31` using the authenticated GitHub account.
2. Inspect the existing files, branches, package metadata, and README.
3. Preserve unrelated work and choose an appropriate feature branch.
4. Add Milestone 1 in small commits with tests and documentation.
5. Run formatting, linting, unit tests, and secret checks.
6. Review the diff for accidental credentials, unsafe execution paths, and unrelated changes.
7. Report the changed files, test results, configuration steps, and any blockers before proceeding to later milestones.

No external message, purchase, deployment, or irreversible action is part of the initial milestone.

## Assumptions and Open Risks

The primary assumption is that the selected repository is intended for this project and either is empty or can accept the proposed Python structure. Existing repository contents may change the exact file layout.

Gemini and OpenRouter APIs, model names, quotas, response formats, and free-tier availability may change. The provider adapters must isolate these differences and expose normalized errors.

WhatsApp Desktop UI automation is inherently brittle and may require selector updates after client releases. It will remain opt-in, dry-run capable, and heavily tested.

Windows security policies, application permissions, antivirus software, and desktop focus behavior may affect automation. The README must document expected permissions and provide diagnostics rather than silently retrying dangerous actions.

SimilarWeb access may require an API plan or an available authenticated relay. The adapter will not assume that a sandbox-only data API is directly callable from the user’s Windows machine; this boundary must be confirmed during implementation.

The user has not specified a preferred UI beyond the supplied CLI-oriented brief, so the first release will use a terminal interface and defer a tray/dashboard UI.

## Definition of Done for the First Approved Build

The first approved build is complete when the repository contains a documented, tested Milestone 1 implementation with dual-provider routing, fallback behavior, strict structured tool validation, a dispatcher skeleton with risk tiers, confirmation hooks, audit logging, safe mock tools, `.env.example`, and no arbitrary command execution. The remaining milestones will be tracked as subsequent increments rather than being implemented all at once.

## UI Amendment — Desktop Command Center

The first executable experience is now a proper Python desktop application rather than a terminal-only program. `ui.py` uses Tkinter and Canvas to provide a dark three-panel HUD layout with telemetry and permission status on the left, an animated central visualizer, and a right-side interaction console. The UI exposes `LISTENING`, `THINKING`, and `SPEAKING` states, an interrupt control, diagnostics, and activity logs.

The top-right `API CONFIG` panel accepts masked Gemini and OpenRouter API keys, supports temporary reveal, allows provider-order editing, and applies configuration without restarting. The values are stored locally in `.env` and deliberately excluded from chat and audit records. Windows Credential Manager integration remains a future hardening step for stronger at-rest secret protection.
