"""Tkinter desktop interface for Jarvis.

The UI is intentionally dependency-light so it can launch on a fresh Windows
Python installation. It provides the visual shell, API configuration, chat
execution, diagnostics, and confirmation surface for the existing safe core.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from config import Settings
from main import build_runtime
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
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.settings = Settings.from_env()
        self.router, self.dispatcher, self.registry = build_runtime(self.settings)
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
            font=("Segoe UI", 25, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="LOCAL COMMAND CENTER  //  PERSONAL AI AUTOMATION",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Consolas", 9),
        ).grid(row=1, column=0, sticky="w")
        self.connection_label = tk.Label(
            header,
            text="●  CORE ONLINE",
            bg=COLORS["bg"],
            fg=COLORS["green"],
            font=("Consolas", 10, "bold"),
        )
        self.connection_label.grid(row=0, column=1, rowspan=2, sticky="e", padx=(0, 18))
        ttk.Button(header, text="API CONFIG", style="Jarvis.TButton", command=self._open_api_config).grid(
            row=0, column=2, rowspan=2, sticky="e"
        )

    def _panel(self, parent: tk.Misc, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        tk.Label(
            frame,
            text=title,
            bg=COLORS["panel"],
            fg=COLORS["cyan"],
            font=("Consolas", 10, "bold"),
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
        panel = self._panel(self, "INTERACTION CONSOLE")
        panel.grid(row=1, column=2, sticky="nsew", padx=(10, 26), pady=8)
        panel.configure(width=360)
        panel.pack_propagate(False)
        self.chat = ScrolledText(panel, wrap="word", height=20, bg="#07111d", fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", borderwidth=0, font=("Consolas", 9), padx=12, pady=10)
        self.chat.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.chat.configure(state="disabled")
        self.chat.tag_configure("system", foreground=COLORS["muted"])
        self.chat.tag_configure("user", foreground=COLORS["cyan"])
        self.chat.tag_configure("jarvis", foreground=COLORS["green"])
        self.chat.tag_configure("error", foreground=COLORS["red"])
        compose = tk.Frame(panel, bg=COLORS["panel"])
        compose.pack(fill="x", padx=12, pady=(0, 14))
        self.input = tk.Entry(compose, bg="#0d2030", fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", font=("Segoe UI", 10))
        self.input.pack(side="left", fill="x", expand=True, ipady=9)
        self.input.bind("<Return>", lambda _event: self._send())
        ttk.Button(compose, text="SEND", style="Jarvis.TButton", command=self._send).pack(side="right", padx=(8, 0))

    def _build_footer(self) -> None:
        footer = tk.Frame(self, bg=COLORS["bg"])
        footer.grid(row=2, column=0, columnspan=3, sticky="ew", padx=26, pady=(0, 18))
        footer.grid_columnconfigure(0, weight=1)
        self.footer_status = tk.Label(footer, text="SYSTEM READY // SAFE MODE ENABLED", bg=COLORS["bg"], fg=COLORS["muted"], font=("Consolas", 8))
        self.footer_status.grid(row=0, column=0, sticky="w")
        tk.Label(footer, text="GEMINI + OPENROUTER FAILOVER", bg=COLORS["bg"], fg=COLORS["cyan_dim"], font=("Consolas", 8)).grid(row=0, column=1, sticky="e")

    def _send(self) -> None:
        command = self.input.get().strip()
        if not command:
            return
        self.input.delete(0, "end")
        self._write_log("YOU", command, COLORS["cyan"])
        self._set_state("THINKING", "ROUTING REQUEST")
        threading.Thread(target=self._run_command, args=(command,), daemon=True).start()

    def _run_command(self, command: str) -> None:
        try:
            response = self.router.run_tool_loop(command, self.registry.all(), self.dispatcher)
            self.events.put(("response", response or "Action completed."))
        except Exception as exc:
            self.events.put(("error", f"{type(exc).__name__}: {exc}"))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "response":
                    self._write_log("JARVIS", str(payload), COLORS["green"])
                    self._set_state("SPEAKING", "RESPONSE READY")
                    self.after(1300, lambda: self._set_state("LISTENING", "READY FOR COMMAND"))
                else:
                    self._write_log("ERROR", str(payload), COLORS["red"])
                    self._set_state("LISTENING", "REQUEST FAILED")
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _write_log(self, speaker: str, text: str, color: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{speaker}\n", (speaker.lower() if speaker.lower() in {"system", "user", "jarvis", "error"} else "system",))
        self.chat.insert("end", f"{text}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _set_state(self, state: str, subtitle: str) -> None:
        self.ui_state = state
        self.state_label.configure(text=state, fg=COLORS["red"] if state == "THINKING" else COLORS["cyan"])
        self.state_subtitle.configure(text=subtitle)
        self.footer_status.configure(text=f"SYSTEM {state} // SAFE MODE ENABLED")
        self._draw_hud()

    def _focus_input(self) -> None:
        self.input.focus_set()

    def _interrupt(self) -> None:
        self._set_state("LISTENING", "INTERRUPT REQUESTED")
        self._write_log("SYSTEM", "Interrupt requested. Active provider calls cannot be cancelled retroactively.", COLORS["orange"])

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

    def _open_api_config(self) -> None:
        window = tk.Toplevel(self)
        window.title("JARVIS // API CONFIGURATION")
        window.configure(bg=COLORS["bg"])
        window.geometry("560x440")
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
        fields = []
        for row, label, variable in ((0, "GEMINI API KEY", gemini_var), (1, "OPENROUTER API KEY", openrouter_var), (2, "PROVIDER ORDER", order_var)):
            tk.Label(form, text=label, bg=COLORS["bg"], fg=COLORS["muted"], font=("Consolas", 8, "bold")).grid(row=row * 2, column=0, sticky="w", pady=(8, 4))
            entry = tk.Entry(form, textvariable=variable, bg="#0d2030", fg=COLORS["text"], insertbackground=COLORS["cyan"], relief="flat", font=("Consolas", 10), show="•" if row < 2 else "")
            entry.grid(row=row * 2 + 1, column=0, sticky="ew", ipady=8)
            fields.append(entry)
        form.grid_columnconfigure(0, weight=1)
        show_var = tk.BooleanVar(value=False)
        def toggle_keys() -> None:
            for entry in fields[:2]:
                entry.configure(show="" if show_var.get() else "•")
        tk.Checkbutton(window, text="SHOW API KEYS", variable=show_var, command=toggle_keys, bg=COLORS["bg"], fg=COLORS["muted"], selectcolor=COLORS["panel"], activebackground=COLORS["bg"], activeforeground=COLORS["cyan"], font=("Consolas", 8)).pack(anchor="w", padx=28, pady=14)
        buttons = tk.Frame(window, bg=COLORS["bg"])
        buttons.pack(fill="x", padx=28, pady=12)
        ttk.Button(buttons, text="CANCEL", style="Jarvis.TButton", command=window.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text="SAVE + APPLY", style="Jarvis.TButton", command=lambda: self._save_api_config(window, gemini_var.get(), openrouter_var.get(), order_var.get())).pack(side="right")

    def _save_api_config(self, window: tk.Toplevel, gemini_key: str, openrouter_key: str, order: str) -> None:
        try:
            values = dict(os.environ)
            values.update({"GEMINI_API_KEY": gemini_key.strip(), "OPENROUTER_API_KEY": openrouter_key.strip(), "JARVIS_PROVIDER_ORDER": order.strip()})
            new_settings = Settings.from_env(values)
            write_local_env(gemini_key.strip(), openrouter_key.strip(), order.strip())
            os.environ.update({"GEMINI_API_KEY": gemini_key.strip(), "OPENROUTER_API_KEY": openrouter_key.strip(), "JARVIS_PROVIDER_ORDER": order.strip()})
            self.settings = new_settings
            self.router, self.dispatcher, self.registry = build_runtime(self.settings)
            self.connection_label.configure(text="●  CONFIGURED", fg=COLORS["green"])
            self._write_log("SYSTEM", "Provider configuration saved locally and applied.", COLORS["green"])
            window.destroy()
        except Exception as exc:
            messagebox.showerror("Configuration error", str(exc), parent=window)

    def _close(self) -> None:
        self.destroy()



def run_app() -> None:
    app = JarvisApp()
    app.mainloop()


__all__ = ["JarvisApp", "run_app"]
