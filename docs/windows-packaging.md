# Mark-31 Standalone Windows Application

Mark-31 can be built as a windowed `Mark31Jarvis.exe` with PyInstaller. Build it on Windows because the application includes Windows-only input, window, audio, screen, camera, tray, and system-control dependencies.

## Build

Open PowerShell in the repository and run `./build_windows.ps1`. The script installs the optional Windows, multimodal, and voice dependencies, installs the Playwright Chromium browser, installs PyInstaller, and produces `dist/Mark31Jarvis.exe`.

## First launch

The first launch opens the existing provider configuration flow. API keys remain local and masked in the UI. Configure allowed local roots before enabling file, video, screenshot, or knowledge operations. Do not place `.env` files in backup archives. DPAPI-protected secrets remain tied to the Windows user profile that created them.

## Runtime data

SQLite databases, audit logs, notification history, conversation history, memory, knowledge indexes, routines, scheduler state, and loop state are stored beneath the configured local data root. The application does not require a hosted service for local operation. Use the existing backup manager for manifest-checked local recovery.

## Browser support

Playwright Chromium is installed by the build script. The first interactive browser session may still require the user to complete sign-in, MFA, CAPTCHA, or an account warning manually. Publishing, messaging, purchases, and other irreversible actions remain confirmation-gated.

## Startup and uninstall

Startup registration is optional and user-controlled. Disable the startup launcher before uninstalling. Uninstalling the executable does not automatically erase local memory, logs, or backups; remove those separately only after confirming that recovery copies are no longer needed.

## Diagnostics

If the UI does not start, run `Mark31Jarvis.exe --cli` from PowerShell to inspect provider configuration, registered tools, audit path, and local database paths. For hardware-specific issues, verify Windows microphone/camera permissions, display capture permission, Playwright browser installation, and optional Windows packages.
