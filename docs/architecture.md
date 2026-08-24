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
