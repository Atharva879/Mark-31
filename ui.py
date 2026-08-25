"""Tkinter desktop interface for Jarvis.

The UI is intentionally dependency-light so it can launch on a fresh Windows
Python installation. It provides the visual shell, API configuration, chat
execution, diagnostics, and confirmation surface for the existing safe core.
"""

from __future__ import annotations

import base64
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from config import Settings
from main import build_runtime
from skills.screen import ScreenCapture
from skills.voice import SpeechSynthesizer, VoiceInput
from skills.web import WebClient
from skills.multimodal import MultimodalIngestor
from memory.long_term import LongTermMemory
from ui_config import write_local_env

try:
    import psutil
except ImportError:  # pragma: no cover - optional until Windows extras are installed
    psutil = None


COLORS = {
    "bg": "#050b13",
    "panel": "#0a1522",
    "panel_alt": "#0e1d2d",
    "line": "#17354a",
    "cyan": "#00d9ff",
    "cyan_dim": "#167b99",
    "text": "#d5edf5",
    "muted": "#6e8ca3",
    "green": "#47f0a1",
    "orange": "#f5b34c",
    "red": "#ff5c78",
}


class JarvisApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JARVIS // Local Command Center")
        self.geometry("1450x860")
        self.minsize(1120, 700)
        self.configure(bg=COLORS["bg"])
        self.tk.call("tk", "scaling", 1.25)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.chat_mode = False
        self.chat_window: tk.Toplevel | None = None
        self.memory_window: tk.Toplevel | None = None
        self.memory_records: list[dict[str, object]] = []

        self.settings = Settings.from_env()
        self.memory = LongTermMemory(self.settings.memory_db_path, self.settings.vector_db_path)
        self.router, self.dispatcher, self.registry = self._build_runtime()
        self.screen = ScreenCapture(timeout_seconds=float(os.environ.get("JARVIS_SCREEN_TIMEOUT_SECONDS", "60")))
        self.web = WebClient(
            timeout_seconds=float(os.environ.get("JARVIS_WEB_TIMEOUT_SECONDS", "15")),
            max_response_bytes=int(os.environ.get("JARVIS_WEB_MAX_RESPONSE_BYTES", "1000000")),
            max_results=int(os.environ.get("JARVIS_WEB_MAX_RESULTS", "5")),
            allowed_hosts={item.strip().lower() for item in os.environ.get("JARVIS_WEB_ALLOWED_HOSTS", "").split(",") if item.strip()},
        )
        self.multimodal = MultimodalIngestor(
            self.settings.allowed_roots,
            max_bytes=int(os.environ.get("JARVIS_MULTIMODAL_MAX_BYTES", "12000000")),
            max_chars=int(os.environ.get("JARVIS_DOCUMENT_MAX_CHARS", "80000")),
        ) if self.settings.allowed_roots else None
        self.voice_input = VoiceInput(
            model_size=os.environ.get("JARVIS_WHISPER_MODEL", "base"),
            max_seconds=float(os.environ.get("JARVIS_VOICE_MAX_SECONDS", "10")),
        )
        self.tts = SpeechSynthesizer(rate=int(os.environ.get("JARVIS_TTS_RATE", "175")))
        self.voice_request_active = False
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.ui_state = "LISTENING"
        self._animation_tick = 0
        self._build_styles()
        self._build_ui()
        self._write_log("SYSTEM", "Jarvis desktop interface initialized.", COLORS["green"])
        self._write_log("SYSTEM", "Paste provider keys from API CONFIG to connect.", COLORS["muted"])
        self._animate_hud()
        self._refresh_telemetry()
        self.after(100, self._drain_events)

    def _build_runtime(self):
        return build_runtime(self.settings, confirm=self._confirm_sensitive_action, notify=self._notify_tool)

    def _confirm_sensitive_action(self, prompt: str) -> bool:
        return messagebox.askyesno("Confirm sensitive action", prompt, parent=self)

    def _notify_tool(self, message: str) -> None:
        self.events.put(("notification", message))

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Jarvis.TButton",
            background=COLORS["panel_alt"],
            foreground=COLORS["cyan"],
            bordercolor=COLORS["cyan_dim"],
            lightcolor=COLORS["cyan_dim"],
            darkcolor=COLORS["panel"],
            padding=(14, 8),
            font=("Segoe UI", 9, "bold"),
        )
        style.map("Jarvis.TButton", background=[("active", "#123149")])
        style.configure(
            "Jarvis.Horizontal.TProgressbar",
            troughcolor=COLORS["panel_alt"],
            background=COLORS["cyan"],
            bordercolor=COLORS["line"],
            lightcolor=COLORS["cyan"],
            darkcolor=COLORS["cyan"],
        )

    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_left_telemetry()
        self._build_center_hud()
        self._build_right_console()
        self._build_footer()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COLORS["bg"], height=72)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=26, pady=(18, 8))
        header.grid_columnconfigure(1, weight=1)
        tk.Label(
            header,
            text="JARVIS",
            bg=COLORS["bg"],
            fg=COLORS["cyan"],
            font=("Segoe UI", 26, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="LOCAL COMMAND CENTER  //  PERSONAL AI AUTOMATION",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Cascadia Mono", 9),
        ).grid(row=1, column=0, sticky="w")
        status_cluster = tk.Frame(header, bg=COLORS["bg"])
        status_cluster.grid(row=0, column=1, rowspan=2, sticky="e", padx=(0, 18))
        self.connection_label = tk.Label(status_cluster, text="●  CORE ONLINE", bg=COLORS["bg"], fg=COLORS["green"], font=("Cascadia Mono", 10, "bold"))
        self.connection_label.pack(anchor="e")
        self.screen_indicator = tk.Label(status_cluster, text="○  SCREEN OFF", bg=COLORS["bg"], fg=COLORS["muted"], font=("Cascadia Mono", 8))
        self.screen_indicator.pack(anchor="e", pady=(3, 0))
        tk.Label(status_cluster, text="●  WEB READY", bg=COLORS["bg"], fg=COLORS["green"], font=("Cascadia Mono", 8)).pack(anchor="e", pady=(3, 0))
        tk.Label(status_cluster, text="●  MEDIA READY" if self.multimodal else "○  MEDIA OFF", bg=COLORS["bg"], fg=COLORS["green"] if self.multimodal else COLORS["muted"], font=("Cascadia Mono", 8)).pack(anchor="e", pady=(3, 0))
        tk.Label(status_cluster, text="●  AGENTS READY", bg=COLORS["bg"], fg=COLORS["green"], font=("Cascadia Mono", 8)).pack(anchor="e", pady=(3, 0))
        actions = tk.Frame(header, bg=COLORS["bg"])
        actions.grid(row=0, column=2, rowspan=2, sticky="e")
        ttk.Button(actions, text="MEMORY", style="Jarvis.TButton", command=self._open_memory_manager).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="API CONFIG", style="Jarvis.TButton", command=self._open_api_config).pack(side="left")

    def _panel(self, parent: tk.Misc, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        tk.Label(
            frame,
            text=title,
            bg=COLORS["panel"],
            fg=COLORS["cyan"],
            font=("Cascadia Mono", 10, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(14, 12))
        return frame

    def _build_left_telemetry(self) -> None:
        panel = self._panel(self, "SYSTEM TELEMETRY")
        panel.grid(row=1, column=0, sticky="nsew", padx=(26, 10), pady=8)
        panel.configure(width=245)
        panel.pack_propagate(False)
        self.telemetry_values: dict[str, tk.Label] = {}
        self.telemetry_bars: dict[str, ttk.Progressbar] = {}
        for key, label in (("cpu", "CPU LOAD"), ("ram", "MEMORY"), ("disk", "DISK")):
            block = tk.Frame(panel, bg=COLORS["panel"])
            block.pack(fill="x", padx=16, pady=10)
            row = tk.Frame(block, bg=COLORS["panel"])
            row.pack(fill="x")
            tk.Label(row, text=label, bg=COLORS["panel"], fg=COLORS["muted"], font=("Consolas", 8)).pack(side="left")
            value = tk.Label(row, text="--%", bg=COLORS["panel"], fg=COLORS["text"], font=("Consolas", 9, "bold"))
            value.pack(side="right")
            self.telemetry_values[key] = value
            bar = ttk.Progressbar(block, style="Jarvis.Horizontal.TProgressbar", maximum=100)
            bar.pack(fill="x", pady=(7, 0))
            self.telemetry_bars[key] = bar

        divider = tk.Frame(panel, bg=COLORS["line"], height=1)
        divider.pack(fill="x", padx=16, pady=18)
        self._side_readout(panel, "HOST", os.environ.get("COMPUTERNAME", "LOCAL WORKSTATION"))
        self._side_readout(panel, "RUNTIME", "PYTHON 3.11+")
        self._side_readout(panel, "MODE", "SAFE EXECUTION")
        self._side_readout(panel, "TOOLS", str(len(self.registry.all())))

        tk.Label(panel, text="PERMISSION MATRIX", bg=COLORS["panel"], fg=COLORS["cyan"], font=("Consolas", 8, "bold")).pack(
            anchor="w", padx=16, pady=(24, 8)
        )
        for name, color, detail in (("SAFE", COLORS["green"], "AUTO"), ("MODERATE", COLORS["orange"], "LOG + NOTIFY"), ("SENSITIVE", COLORS["red"], "CONFIRM")):
            row = tk.Frame(panel, bg=COLORS["panel"])
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(row, text="●", bg=COLORS["panel"], fg=color, font=("Consolas", 9)).pack(side="left")
            tk.Label(row, text=name, bg=COLORS["panel"], fg=COLORS["text"], font=("Consolas", 8, "bold")).pack(side="left", padx=7)
            tk.Label(row, text=detail, bg=COLORS["panel"], fg=COLORS["muted"], font=("Consolas", 7)).pack(side="right")

    def _side_readout(self, parent: tk.Misc, key: str, value: str) -> None:
        row = tk.Frame(parent, bg=COLORS["panel"])
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text=key, bg=COLORS["panel"], fg=COLORS["muted"], font=("Consolas", 8)).pack(side="left")
        tk.Label(row, text=value[:24], bg=COLORS["panel"], fg=COLORS["text"], font=("Consolas", 8)).pack(side="right")

    def _build_center_hud(self) -> None:
        panel = tk.Frame(self, bg=COLORS["bg"])
        panel.grid(row=1, column=1, sticky="nsew", padx=10, pady=8)
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self.hud = tk.Canvas(panel, bg=COLORS["bg"], highlightthickness=0)
        self.hud.grid(row=0, column=0, sticky="nsew")
        self.hud.bind("<Configure>", lambda _event: self._draw_hud())
        self.state_label = tk.Label(panel, text="LISTENING", bg=COLORS["bg"], fg=COLORS["cyan"], font=("Consolas", 16, "bold"))
        self.state_label.grid(row=1, column=0, pady=(0, 8))
        self.state_subtitle = tk.Label(panel, text="READY FOR COMMAND", bg=COLORS["bg"], fg=COLORS["muted"], font=("Consolas", 8))
        self.state_subtitle.grid(row=2, column=0, pady=(0, 18))
        controls = tk.Frame(panel, bg=COLORS["bg"])
        controls.grid(row=3, column=0, pady=(0, 18))
        ttk.Button(controls, text="INITIALIZE", style="Jarvis.TButton", command=self._focus_input).pack(side="left", padx=5)
        self.screen_button = ttk.Button(controls, text="ENABLE SCREEN", style="Jarvis.TButton", command=self._toggle_screen)
        self.screen_button.pack(side="left", padx=5)
        self.chat_mode_button = ttk.Button(controls, text="ENABLE CHAT MODE", style="Jarvis.TButton", command=self._toggle_chat_mode)
        self.chat_mode_button.pack(side="left", padx=5)
        self.voice_button = ttk.Button(controls, text="START VOICE", style="Jarvis.TButton", command=self._start_voice)
        self.voice_button.pack(side="left", padx=5)
        ttk.Button(controls, text="INTERRUPT", style="Jarvis.TButton", command=self._interrupt).pack(side="left", padx=5)

    def _draw_hud(self) -> None:
        self.hud.delete("all")
        width = max(self.hud.winfo_width(), 420)
        height = max(self.hud.winfo_height(), 420)
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.32
        pulse = (self._animation_tick % 18) * 1.3
        accent = COLORS["red"] if self.ui_state == "THINKING" else COLORS["cyan"]
        for index, scale in enumerate((1.0, 0.82, 0.64, 0.46)):
            r = radius * scale + (pulse if index == 0 else 0)
            self.hud.create_oval(cx - r, cy - r, cx + r, cy + r, outline=accent if index < 2 else COLORS["cyan_dim"], width=1)
        for angle in range(0, 360, 30):
            import math
            radians = math.radians(angle + self._animation_tick * (1 if angle % 60 == 0 else -1))
            start = radius * 0.88
            end = radius * 1.08
            self.hud.create_line(
                cx + math.cos(radians) * start,
                cy + math.sin(radians) * start,
                cx + math.cos(radians) * end,
                cy + math.sin(radians) * end,
                fill=accent,
                width=2 if angle % 60 == 0 else 1,
            )
        self.hud.create_text(cx, cy - 13, text="J", fill=accent, font=("Segoe UI", 58, "bold"))
        self.hud.create_text(cx, cy + 45, text="CORE", fill=COLORS["muted"], font=("Consolas", 9, "bold"))
        self.hud.create_text(30, 26, text="VISUALIZER // ACTIVE", fill=COLORS["muted"], anchor="w", font=("Consolas", 8))
        self.hud.create_text(width - 30, 26, text=f"T+{self._animation_tick:04d}", fill=COLORS["muted"], anchor="e", font=("Consolas", 8))
        base_y = height - 38
        for index in range(32):
            bar = 3 + ((index * 7 + self._animation_tick * (2 if self.ui_state != "LISTENING" else 1)) % 17)
            x = cx - 124 + index * 8
            self.hud.create_line(x, base_y, x, base_y - bar, fill=accent if index % 3 else COLORS["cyan_dim"], width=2)

    def _build_right_console(self) -> None:
        panel = self._panel(self, "ACTIVITY FEED")
        panel.grid(row=1, column=2, sticky="nsew", padx=(10, 26), pady=8)
        panel.configure(width=360)
        panel.pack_propagate(False)
        self.activity = ScrolledText(panel, wrap="word", height=20, bg="#07111d", fg=COLORS["text"], relief="flat", borderwidth=0, font=("Segoe UI", 9), padx=14, pady=12)
        self.activity.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.activity.configure(state="disabled")
        self.activity.tag_configure("system", foreground=COLORS["muted"], font=("Cascadia Mono", 8, "bold"))
        self.activity.tag_configure("user", foreground=COLORS["cyan"], font=("Cascadia Mono", 8, "bold"))
        self.activity.tag_configure("jarvis", foreground=COLORS["green"], font=("Cascadia Mono", 8, "bold"))
        self.activity.tag_configure("error", foreground=COLORS["red"], font=("Cascadia Mono", 8, "bold"))
        tk.Label(panel, text="CHAT MODE OFF  //  ACTIVITY-ONLY VIEW", bg=COLORS["panel"], fg=COLORS["muted"], font=("Cascadia Mono", 8)).pack(anchor="w", padx=16, pady=(0, 14))

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg=COLORS["bg"])
        footer.grid(row=2, column=0, columnspan=3, sticky="ew", padx=26, pady=(0, 18))
        footer.grid_columnconfigure(0, weight=1)
        self.footer_status = tk.Label(footer, text="SYSTEM READY // SAFE MODE ENABLED", bg=COLORS["bg"], fg=COLORS["muted"], font=("Consolas", 8))
        self.footer_status.grid(row=0, column=0, sticky="w")
        tk.Label(footer, text="GEMINI + OPENROUTER FAILOVER", bg=COLORS["bg"], fg=COLORS["cyan_dim"], font=("Consolas", 8)).grid(row=0, column=1, sticky="e")

    def _send(self) -> None:
        if not self.chat_mode or not hasattr(self, "input"):
            self._write_log("SYSTEM", "Enable Chat Mode before entering a direct command.", COLORS["orange"])
            return
        command = self.input.get().strip()
        if not command:
            return
        self.input.delete(0, "end")
        self._write_log("YOU", command, COLORS["cyan"])
        self._set_state("THINKING", "ANALYZING REQUEST")
        threading.Thread(target=self._run_command, args=(command,), daemon=True).start()

    def _run_command(self, command: str) -> None:
        try:
            lowered = command.lower()
            if lowered.startswith("/screen "):
                response = self._analyze_screen(command[8:].strip())
            elif lowered.startswith("/search "):
                response = self._search_web(command[8:].strip())
            elif lowered.startswith("/fetch "):
                response = self._fetch_web(command[7:].strip())
            elif lowered.startswith("/image "):
                response = self._analyze_image_command(command[7:].strip())
            elif lowered.startswith("/document "):
                response = self._analyze_document_command(command[10:].strip())
            else:
                response = self.router.run_tool_loop(command, self.registry.all(), self.dispatcher)
            self.events.put(("response", response or "Action completed."))
        except Exception as exc:
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))

    def _search_web(self, query: str) -> str:
        results = self.web.search(query)
        if not results:
            return "No public web results found."
        return "\n\n".join(f"{index}. {item['title']}\n{item['url']}\n{item['snippet']}" for index, item in enumerate(results, 1))

    def _fetch_web(self, url: str) -> str:
        payload = self.web.fetch_url(url)
        return f"{payload['url']}\n[{payload['content_type']}] retrieved {payload['retrieved_at']}\n\n{payload['content']}"

    def _analyze_image_command(self, value: str) -> str:
        if self.multimodal is None:
            raise PermissionError("Configure JARVIS_ALLOWED_ROOTS before analyzing local images")
        path, prompt = _split_asset_command(value, "Describe this image and identify important details.")
        payload = self.multimodal.inspect_image(path)
        provider = self.router.providers.get("gemini")
        if provider is None or not hasattr(provider, "analyze_image"):
            raise RuntimeError("Gemini vision provider is unavailable")
        response = provider.analyze_image(payload.png_bytes, prompt)
        return f"{payload.path} ({payload.width}x{payload.height})\n\n{response.content}"

    def _analyze_document_command(self, value: str) -> str:
        if self.multimodal is None:
            raise PermissionError("Configure JARVIS_ALLOWED_ROOTS before analyzing local documents")
        path, prompt = _split_asset_command(value, "Summarize this document and list its key points.")
        payload = self.multimodal.extract_document(path)
        response = self.router.analyze_document(payload.text, prompt)
        suffix = " (truncated to the configured limit)" if payload.truncated else ""
        return f"{payload.path}{suffix}\n\n{response}"

    def _analyze_screen(self, prompt: str) -> str:
        if not self.screen.status().active:
            raise PermissionError("Enable Screen Awareness before using /screen analysis")
        provider = self.router.providers.get("gemini")
        if provider is None or not hasattr(provider, "analyze_image"):
            raise RuntimeError("Gemini vision provider is unavailable")
        image = base64.b64decode(self.screen.capture_png_base64())
        return provider.analyze_image(image, prompt or "Describe the visible screen and identify any obvious issue.").content

    def _toggle_screen(self) -> None:
        if self.screen.status().active:
            self.screen.disable("user_toggle")
            self.screen_button.configure(text="ENABLE SCREEN")
            self.screen_indicator.configure(text="○  SCREEN OFF", fg=COLORS["muted"])
            self._write_log("SYSTEM", "Screen awareness disabled. No screenshot is active.", COLORS["muted"])
        else:
            self.screen.enable("user_toggle")
            self.screen_button.configure(text="DISABLE SCREEN")
            self.screen_indicator.configure(text="●  SCREEN ACTIVE", fg=COLORS["red"])
            self._write_log("SYSTEM", "Screen awareness enabled for a limited session. Use /screen <question>.", COLORS["orange"])


    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "notification":
                    self._write_log("SYSTEM", str(payload), COLORS["orange"])
                elif kind == "memory_records":
                    self._render_memory_records(payload)
                elif kind == "memory_status":
                    if hasattr(self, "memory_status_label") and self.memory_status_label.winfo_exists():
                        self.memory_status_label.configure(text=str(payload), fg=COLORS["muted"])
                elif kind == "memory_error":
                    if hasattr(self, "memory_status_label") and self.memory_status_label.winfo_exists():
                        self.memory_status_label.configure(text=str(payload), fg=COLORS["red"])
                elif kind == "response":
                    self._write_log("JARVIS", str(payload), COLORS["green"])
                    if self.voice_request_active:
                        self._set_state("SPEAKING", "VOICE RESPONSE")
                        self.tts.speak_async(str(payload), on_done=lambda: self.events.put(("speech_done", "")))
                    else:
                        self._set_state("SPEAKING", "RESPONSE READY")
                        self.after(1300, lambda: self._set_state("LISTENING", "READY FOR COMMAND"))
                elif kind == "voice_transcript":
                    self._write_log("VOICE", str(payload), COLORS["cyan"])
                elif kind == "voice_thinking":
                    self._set_state("THINKING", "ROUTING VOICE COMMAND")
                elif kind == "speech_done":
                    self.voice_request_active = False
                    self.voice_button.configure(state="normal", text="START VOICE")
                    self._set_state("LISTENING", "READY FOR COMMAND")
                else:
                    self.voice_request_active = False
                    self.voice_button.configure(state="normal", text="START VOICE")
                    self._write_log("ERROR", str(payload), COLORS["red"])
                    self._set_state("LISTENING", "REQUEST FAILED")
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _write_log(self, speaker: str, text: str, color: str) -> None:
        tag = speaker.lower() if speaker.lower() in {"system", "user", "jarvis", "error"} else "system"
        for view in (getattr(self, "activity", None), getattr(self, "chat_view", None)):
            if view is None or not view.winfo_exists():
                continue
            view.configure(state="normal")
            view.insert("end", f"{speaker}\n", tag)
            view.insert("end", f"{text}\n\n")
            view.see("end")
            view.configure(state="disabled")

    def _set_state(self, state: str, subtitle: str) -> None:
        self.ui_state = state
        self.state_label.configure(text=state, fg=COLORS["red"] if state == "THINKING" else COLORS["cyan"])
        self.state_subtitle.configure(text=subtitle)
        self.footer_status.configure(text=f"SYSTEM {state} // SAFE MODE ENABLED")
        self._draw_hud()

    def _focus_input(self) -> None:
        if not self.chat_mode:
            self._toggle_chat_mode()
        if self.chat_mode and hasattr(self, "input"):
            self.input.focus_set()

    def _toggle_chat_mode(self) -> None:
        if self.chat_mode:
            self._close_chat_mode()
            return
        self.chat_mode = True
        self.chat_mode_button.configure(text="DISABLE CHAT MODE")
        self.chat_window = tk.Toplevel(self)
        self.chat_window.title("JARVIS // CHAT MODE")
        self.chat_window.configure(bg=COLORS["bg"])
        self.chat_window.geometry("660x560")
        self.chat_window.minsize(520, 420)
        self.chat_window.transient(self)
        self.chat_window.protocol("WM_DELETE_WINDOW", self._close_chat_mode)
        tk.Label(self.chat_window, text="CHAT MODE", bg=COLORS["bg"], fg=COLORS["cyan"], font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=24, pady=(22, 3))
        tk.Label(self.chat_window, text="Direct conversation is enabled only while this window is open.", bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(0, 16))
        self.chat_view = ScrolledText(self.chat_window, wrap="word", bg="#07111d", fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", borderwidth=0, font=("Segoe UI", 10), padx=14, pady=12)
        self.chat_view.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        self.chat_view.configure(state="disabled")
        compose = tk.Frame(self.chat_window, bg=COLORS["bg"])
        compose.pack(fill="x", padx=24, pady=(0, 22))
        self.input = tk.Entry(compose, bg="#0d2030", fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", font=("Segoe UI", 11))
        self.input.pack(side="left", fill="x", expand=True, ipady=10)
        self.input.bind("<Return>", lambda _event: self._send())
        ttk.Button(compose, text="SEND", style="Jarvis.TButton", command=self._send).pack(side="right", padx=(8, 0))
        self.input.focus_set()

    def _close_chat_mode(self) -> None:
        self.chat_mode = False
        self.chat_mode_button.configure(text="ENABLE CHAT MODE")
        if self.chat_window is not None and self.chat_window.winfo_exists():
            self.chat_window.destroy()
        self.chat_window = None

    def _start_voice(self) -> None:
        if self.voice_request_active:
            return
        self.voice_request_active = True
        self.voice_button.configure(state="disabled", text="LISTENING...")
        self._set_state("LISTENING", "MICROPHONE ACTIVE")
        self._write_log("SYSTEM", "Push-to-talk capture started. Audio stays local for transcription.", COLORS["orange"])
        threading.Thread(target=self._listen_and_run, daemon=True).start()

    def _listen_and_run(self) -> None:
        try:
            text = self.voice_input.listen_once()
            if not text:
                raise RuntimeError("No speech was detected")
            self.events.put(("voice_transcript", text))
            self.events.put(("voice_thinking", ""))
            self._run_command(text)
        except Exception as exc:
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))

    def _interrupt(self) -> None:
        self.tts.stop()
        self.voice_request_active = False
        self.voice_button.configure(state="normal", text="START VOICE")
        self._set_state("LISTENING", "INTERRUPT REQUESTED")
        self._write_log("SYSTEM", "Interrupt requested. Speech output stopped; active network calls cannot be cancelled retroactively.", COLORS["orange"])

    def _refresh_telemetry(self) -> None:
        if psutil is None:
            values = {"cpu": 0, "ram": 0, "disk": 0}
        else:
            values = {
                "cpu": psutil.cpu_percent(interval=None),
                "ram": psutil.virtual_memory().percent,
                "disk": psutil.disk_usage(Path.home().anchor or "/").percent,
            }
        for key, value in values.items():
            self.telemetry_values[key].configure(text=f"{value:.0f}%")
            self.telemetry_bars[key]["value"] = value
        self.after(1500, self._refresh_telemetry)

    def _animate_hud(self) -> None:
        self._animation_tick = (self._animation_tick + 1) % 10000
        self._draw_hud()
        self.after(90, self._animate_hud)

    def _open_memory_manager(self) -> None:
        if self.memory_window is not None and self.memory_window.winfo_exists():
            self.memory_window.deiconify()
            self.memory_window.lift()
            return
        window = tk.Toplevel(self)
        self.memory_window = window
        window.title("JARVIS // MEMORY MANAGEMENT")
        window.configure(bg=COLORS["bg"])
        window.geometry("980x650")
        window.minsize(760, 500)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_memory_manager)

        heading = tk.Frame(window, bg=COLORS["bg"])
        heading.pack(fill="x", padx=24, pady=(22, 8))
        tk.Label(heading, text="MEMORY MANAGEMENT", bg=COLORS["bg"], fg=COLORS["cyan"], font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(heading, text="Inspect durable facts and their local vector index. Deletion is permanent and requires confirmation.", bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        search = tk.Frame(window, bg=COLORS["bg"])
        search.pack(fill="x", padx=24, pady=(8, 12))
        self.memory_query = tk.StringVar()
        query_entry = tk.Entry(search, textvariable=self.memory_query, bg="#0d2030", fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", font=("Segoe UI", 10))
        query_entry.pack(side="left", fill="x", expand=True, ipady=9)
        query_entry.bind("<Return>", lambda _event: self._memory_search())
        self.memory_mode = tk.StringVar(value="SEMANTIC")
        ttk.Combobox(search, textvariable=self.memory_mode, values=("SEMANTIC", "LEXICAL"), state="readonly", width=11).pack(side="left", padx=8)
        ttk.Button(search, text="SEARCH", style="Jarvis.TButton", command=self._memory_search).pack(side="left")

        table_frame = tk.Frame(window, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        table_frame.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        columns = ("id", "kind", "content", "tags", "score", "vector")
        self.memory_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {"id": "ID", "kind": "TYPE", "content": "CONTENT", "tags": "TAGS", "score": "SIMILARITY", "vector": "VECTOR"}
        widths = {"id": 55, "kind": 70, "content": 390, "tags": 130, "score": 90, "vector": 80}
        for column in columns:
            self.memory_tree.heading(column, text=headings[column])
            self.memory_tree.column(column, width=widths[column], anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.memory_tree.yview)
        self.memory_tree.configure(yscrollcommand=scrollbar.set)
        self.memory_tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)
        self.memory_tree.bind("<Double-1>", lambda _event: self._show_memory_detail())

        footer = tk.Frame(window, bg=COLORS["bg"])
        footer.pack(fill="x", padx=24, pady=(0, 20))
        self.memory_status_label = tk.Label(footer, text="Loading memory index...", bg=COLORS["bg"], fg=COLORS["muted"], font=("Cascadia Mono", 8))
        self.memory_status_label.pack(side="left")
        ttk.Button(footer, text="REFRESH", style="Jarvis.TButton", command=self._memory_refresh).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="REINDEX", style="Jarvis.TButton", command=self._memory_reindex).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="DELETE SELECTED", style="Jarvis.TButton", command=self._memory_delete_selected).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="CLOSE", style="Jarvis.TButton", command=self._close_memory_manager).pack(side="right")
        self._memory_refresh()

    def _close_memory_manager(self) -> None:
        if self.memory_window is not None and self.memory_window.winfo_exists():
            self.memory_window.destroy()
        self.memory_window = None

    def _memory_refresh(self) -> None:
        if self.memory_window is None or not self.memory_window.winfo_exists():
            return
        self.memory_query.set("")
        self.memory_status_label.configure(text="Loading memory records...", fg=COLORS["muted"])
        threading.Thread(target=self._memory_refresh_worker, daemon=True).start()

    def _memory_refresh_worker(self) -> None:
        try:
            records = self.memory.recent(100)
            self.events.put(("memory_records", records))
            stats = self.memory.stats()
            self.events.put(("memory_status", f"{stats['memory_records']} records  //  {stats['vector_records']} vectors  //  local index"))
        except Exception as exc:
            self.events.put(("memory_error", f"Memory refresh failed: {type(exc).__name__}: {exc}"))

    def _memory_search(self) -> None:
        query = self.memory_query.get().strip()
        if not query:
            self._memory_refresh()
            return
        mode = self.memory_mode.get()
        self.memory_status_label.configure(text=f"Searching {mode.lower()} memory...", fg=COLORS["muted"])
        threading.Thread(target=self._memory_search_worker, args=(query, mode), daemon=True).start()

    def _memory_search_worker(self, query: str, mode: str) -> None:
        try:
            records = self.memory.semantic_recall(query, 100, 0.0) if mode == "SEMANTIC" else self.memory.recall(query, 100)
            self.events.put(("memory_records", records))
            self.events.put(("memory_status", f"{len(records)} {mode.lower()} matches"))
        except Exception as exc:
            self.events.put(("memory_error", f"Memory search failed: {type(exc).__name__}: {exc}"))

    def _render_memory_records(self, records: object) -> None:
        if not hasattr(self, "memory_tree") or not self.memory_tree.winfo_exists():
            return
        self.memory_records = list(records) if isinstance(records, list) else []
        for item in self.memory_tree.get_children():
            self.memory_tree.delete(item)
        for index, record in enumerate(self.memory_records):
            score = record.get("similarity", "—") if isinstance(record, dict) else "—"
            self.memory_tree.insert("", "end", iid=str(index), values=(
                record.get("id", "—"), record.get("kind", "—"), str(record.get("content", ""))[:240],
                str(record.get("tags", ""))[:80], score, "INDEXED" if self.memory.vector_exists(int(record["id"])) else "MISSING",
            ))

    def _show_memory_detail(self) -> None:
        selection = self.memory_tree.selection() if hasattr(self, "memory_tree") else ()
        if not selection:
            return
        record = self.memory_records[int(selection[0])]
        detail = "\\n".join(f"{key.upper()}: {value}" for key, value in record.items())
        messagebox.showinfo("Memory record", detail, parent=self.memory_window)

    def _memory_reindex(self) -> None:
        if not messagebox.askyesno("Reindex memory", "Rebuild the local vector index from all durable memory records?", parent=self.memory_window):
            return
        self.memory_status_label.configure(text="Rebuilding vector index...", fg=COLORS["orange"])
        threading.Thread(target=self._memory_reindex_worker, daemon=True).start()

    def _memory_reindex_worker(self) -> None:
        try:
            count = self.memory.reindex()
            self.events.put(("memory_status", f"Reindexed {count} records successfully"))
            self.events.put(("memory_records", self.memory.recent(100)))
        except Exception as exc:
            self.events.put(("memory_error", f"Reindex failed: {type(exc).__name__}: {exc}"))

    def _memory_delete_selected(self) -> None:
        selection = self.memory_tree.selection() if hasattr(self, "memory_tree") else ()
        if not selection:
            messagebox.showinfo("Delete memory", "Select a memory record first.", parent=self.memory_window)
            return
        record = self.memory_records[int(selection[0])]
        memory_id = int(record["id"])
        preview = str(record.get("content", ""))[:160]
        if not messagebox.askyesno("Delete memory", f"Permanently delete memory #{memory_id}?\\n\\n{preview}", parent=self.memory_window):
            return
        self.memory_status_label.configure(text=f"Deleting memory #{memory_id}...", fg=COLORS["orange"])
        threading.Thread(target=self._memory_delete_worker, args=(memory_id,), daemon=True).start()

    def _memory_delete_worker(self, memory_id: int) -> None:
        try:
            deleted = self.memory.forget(memory_id)
            self.events.put(("memory_status", f"Memory #{memory_id} deleted" if deleted else f"Memory #{memory_id} was not found"))
            self.events.put(("memory_records", self.memory.recent(100)))
        except Exception as exc:
            self.events.put(("memory_error", f"Delete failed: {type(exc).__name__}: {exc}"))

    def _open_api_config(self) -> None:
        window = tk.Toplevel(self)
        window.title("JARVIS // API CONFIGURATION")
        window.configure(bg=COLORS["bg"])
        window.geometry("680x760")
        window.resizable(False, False)
        window.transient(self)
        window.grab_set()
        tk.Label(window, text="API CONFIGURATION", bg=COLORS["bg"], fg=COLORS["cyan"], font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=28, pady=(24, 4))
        tk.Label(window, text="Keys stay local and are never written to chat or audit logs.", bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(anchor="w", padx=28, pady=(0, 22))
        form = tk.Frame(window, bg=COLORS["bg"])
        form.pack(fill="x", padx=28)
        gemini_var = tk.StringVar(value=self.settings.gemini_api_key)
        openrouter_var = tk.StringVar(value=self.settings.openrouter_api_key)
        order_var = tk.StringVar(value=",".join(self.settings.provider_order))
        gemini_model_var = tk.StringVar(value=self.settings.gemini_model)
        openrouter_model_var = tk.StringVar(value=self.settings.openrouter_model)
        local_model_var = tk.StringVar(value=self.settings.local_model)
        local_url_var = tk.StringVar(value=self.settings.local_base_url)
        key_fields = []
        entries = (
            ("GEMINI API KEY", gemini_var, True),
            ("OPENROUTER API KEY", openrouter_var, True),
            ("FALLBACK ORDER", order_var, False),
            ("GEMINI MODEL", gemini_model_var, False),
            ("OPENROUTER MODEL", openrouter_model_var, False),
            ("LOCAL MODEL", local_model_var, False),
            ("LOCAL ENDPOINT", local_url_var, False),
        )
        for row, (label, variable, secret) in enumerate(entries):
            tk.Label(form, text=label, bg=COLORS["bg"], fg=COLORS["muted"], font=("Consolas", 8, "bold")).grid(row=row * 2, column=0, sticky="w", pady=(6, 3))
            entry = tk.Entry(form, textvariable=variable, bg="#0d2030", fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", font=("Consolas", 10), show="•" if secret else "")
            entry.grid(row=row * 2 + 1, column=0, sticky="ew", ipady=7)
            if secret:
                key_fields.append(entry)
        form.grid_columnconfigure(0, weight=1)
        show_var = tk.BooleanVar(value=False)
        def toggle_keys() -> None:
            for entry in key_fields:
                entry.configure(show="" if show_var.get() else "•")
        tk.Checkbutton(window, text="SHOW API KEYS", variable=show_var, command=toggle_keys, bg=COLORS["bg"], fg=COLORS["muted"], selectcolor=COLORS["panel"], activebackground=COLORS["bg"], activeforeground=COLORS["cyan"], font=("Consolas", 8)).pack(anchor="w", padx=28, pady=(12, 8))
        tk.Label(window, text="LOCAL PROVIDERS MUST USE A LOOPBACK ENDPOINT. FALLBACK ORDER ACCEPTS local, gemini, openrouter.", bg=COLORS["bg"], fg=COLORS["cyan_dim"], font=("Cascadia Mono", 7)).pack(anchor="w", padx=28, pady=(0, 8))
        buttons = tk.Frame(window, bg=COLORS["bg"])
        buttons.pack(fill="x", padx=28, pady=12)
        ttk.Button(buttons, text="CANCEL", style="Jarvis.TButton", command=window.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="SAVE + APPLY", style="Jarvis.TButton", command=lambda: self._save_api_config(window, gemini_var.get(), openrouter_var.get(), order_var.get(), gemini_model_var.get(), openrouter_model_var.get(), local_model_var.get(), local_url_var.get())).pack(side="right")

    def _save_api_config(self, window: tk.Toplevel, gemini_key: str, openrouter_key: str, order: str, gemini_model: str, openrouter_model: str, local_model: str, local_url: str) -> None:
        try:
            values = dict(os.environ)
            values.update({"GEMINI_API_KEY": gemini_key.strip(), "OPENROUTER_API_KEY": openrouter_key.strip(), "JARVIS_PROVIDER_ORDER": order.strip(), "GEMINI_MODEL": gemini_model.strip(), "OPENROUTER_MODEL": openrouter_model.strip(), "JARVIS_LOCAL_MODEL": local_model.strip(), "JARVIS_LOCAL_BASE_URL": local_url.strip()})
            new_settings = Settings.from_env(values)
            write_local_env(gemini_key.strip(), openrouter_key.strip(), order.strip(), gemini_model.strip(), openrouter_model.strip(), local_model.strip(), local_url.strip())
            os.environ.update({"GEMINI_API_KEY": gemini_key.strip(), "OPENROUTER_API_KEY": openrouter_key.strip(), "JARVIS_PROVIDER_ORDER": order.strip(), "GEMINI_MODEL": gemini_model.strip(), "OPENROUTER_MODEL": openrouter_model.strip(), "JARVIS_LOCAL_MODEL": local_model.strip(), "JARVIS_LOCAL_BASE_URL": local_url.strip()})
            self.settings = new_settings
            self.router, self.dispatcher, self.registry = self._build_runtime()
            self.connection_label.configure(text="●  CONFIGURED", fg=COLORS["green"])
            self._write_log("SYSTEM", "Provider configuration saved locally and applied.", COLORS["green"])
            window.destroy()
        except Exception as exc:
            messagebox.showerror("Configuration error", str(exc), parent=window)

    def _close(self) -> None:
        self.destroy()



def _split_asset_command(value: str, default_prompt: str) -> tuple[str, str]:
    if not value.strip():
        raise ValueError("Provide a local path")
    if "|" in value:
        path, prompt = value.split("|", 1)
        return path.strip(), prompt.strip() or default_prompt
    return value.strip(), default_prompt


def run_app() -> None:
    app = JarvisApp()
    app.mainloop()


__all__ = ["JarvisApp", "run_app"]
