# Jarvis Presence Behavior Specification

## Purpose

Jarvis Presence adds a restrained proactive layer to the local desktop agent. It allows Jarvis to speak first when the user has been inactive, creating a sense of continuity and awareness without pretending to have consciousness or granting it independent authority.

## Approved behavior

The first eligibility check occurs after **60 seconds of user inactivity**. Eligibility is not a command to speak. The engine may remain quiet when there is no worthwhile observation, when the user is interacting with the computer, or when a recent message already satisfies the moment.

| Control | Default behavior |
|---|---|
| Idle threshold | 60 seconds before an ambient message can be considered |
| Ambient cooldown | At least 10 minutes between casual proactive messages |
| Hourly limit | At most 2 ambient proactive messages per hour |
| Daily limit | At most 20 ambient proactive messages per local day |
| Repetition protection | Do not reuse the same message fingerprint or topic until the recent-message window has moved on |
| Event priority | Important monitor changes, failures, and reminders outrank casual observations and may be grouped |
| Silence | `STAY SILENT` immediately suppresses ambient and event-originated speech until manually resumed |
| Delivery | Text activity-feed notification by default; voice output only when explicitly enabled |

## Message categories

Presence messages may be a short status observation, a gentle offer of help, a scheduled reminder, or a contextual check-in based on approved local state. The first implementation must not invent personal facts, claim emotions, imply hidden perception, or create arbitrary tasks. It must not execute tools merely because it generated a message.

## Context boundary

The engine may read bounded local presence state, recent Jarvis activity labels, scheduler event summaries, and the current time. It must not silently capture the screen, inspect arbitrary files, access the microphone, call external messaging services, or send content to an LLM solely to manufacture chatter. Any future LLM-assisted wording must be optional, bounded, and passed through the same local audit and safety policy.

## Safety and lifecycle

Presence is an output feature, not an execution authority. It never bypasses the dispatcher, confirmation callbacks, scoped file rules, or audit logger. The application must remain open for the feature to operate. All proactive outputs are written to the local audit trail with category and reason metadata, while secrets and raw sensitive content remain excluded.

The user can disable Presence or press `STAY SILENT` at any time. User commands, voice capture, Chat Mode, and shutdown reset or suspend the idle timer as appropriate. The engine must avoid duplicate concurrent emissions and must fail closed—if its state store or context is unavailable, it does nothing rather than guessing.
