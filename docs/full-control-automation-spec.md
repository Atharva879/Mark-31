# Full-Control Desktop Automation Specification

## Purpose

Mark-31 should be able to operate a Windows laptop through the keyboard, mouse, screen, windows, and browser while remaining user-authorized and observable. Full control means broad capability, not silent authority: the assistant may plan and perform actions only through registered adapters that enforce permissions, bounds, audit events, and cancellation.

## Control modes

| Mode | Capability | Default | Confirmation |
|---|---|---:|---|
| Observe | Read active window and bounded screen state | Off | Permission grant required |
| Assist | Move pointer, focus a window, highlight a target, and show a proposed action | Off | User reviews proposal |
| Execute | Type, click, scroll, hotkey, navigate, and interact with an approved window/browser | Off | Per-session approval; sensitive actions still require per-action confirmation |
| Emergency stop | Immediately cancel queued actions and release input control | Always available | No confirmation |

Execute mode expires automatically, is visibly indicated in the HUD and tray, and is revoked when the application closes. Camera access remains separate and is never implied by desktop control.

## Registered action surface

The first implementation will expose bounded actions: move/click at a coordinate inside the visible screen bounds; key presses from an allowlisted key vocabulary; bounded text typing with secret-field protection; scroll; hotkeys from an allowlist; focus or close an identified top-level window; and browser navigation, tab selection, clicking, typing, and scrolling through a dedicated automation adapter. The model cannot emit raw Python, shell commands, arbitrary native messages, or unvalidated automation scripts.

Every action must include an action type, target description, expected foreground application/window, timeout, and cancellation token. Coordinate actions are rejected when the target window or screen geometry differs from the observation used to plan them beyond the configured tolerance. If target identity is uncertain, Mark-31 pauses and asks the user rather than guessing.

## Safety boundaries

Destructive file operations, account changes, purchases, financial actions, credential entry, message sending, form submission, software installation, and security-setting changes remain `SENSITIVE` and require explicit confirmation immediately before execution. Passwords, API keys, one-time codes, and clipboard secrets are never typed automatically. Browser control is not an unrestricted web agent: private-network navigation, downloads, script execution, CAPTCHA bypass, and hidden background browsing remain blocked.

The dispatcher remains the only execution authority. All desktop actions are registered tools with schemas and risk tiers. Routines may use only SAFE tools; full-control actions cannot be smuggled into routine definitions. Audit records store the action type, target application, bounded metadata, result, and cancellation state while redacting text and secrets.

## Emergency stop and recovery

The HUD and tray expose `STOP ALL ACTIONS`. A global cancellation event is checked before every action and between typing/key batches. Emergency stop releases held mouse buttons and modifier keys, cancels queued work, disables Execute mode, and records an audit event. If the automation adapter reports an uncertain state, Mark-31 stops rather than retrying blindly.

## Windows verification requirement

The sandbox can validate schemas, permissions, cancellation, redaction, and fake adapters, but it cannot verify real Tkinter, Windows input injection, window selectors, DPI scaling, or browser-driver behavior. Before enabling Execute mode on the user’s laptop, the feature must pass a Windows test checklist using harmless applications such as Notepad and a local test page. The user must bind/select the Mark-31 Windows folder in Manus Desktop for direct local testing.
