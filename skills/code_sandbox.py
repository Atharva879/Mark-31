"""Best-effort local Python sandbox for small, non-I/O computations.

This is intentionally not presented as a security boundary against a hostile OS user.
It is an agent safety boundary: no shell, imports, file/network APIs, or arbitrary
process creation are available, and every run is resource bounded and isolated in a
short-lived subprocess.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxResult:
    status: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
        }


class CodeSandbox:
    _blocked_nodes = (
        ast.Import,
        ast.ImportFrom,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.Raise,
        ast.Delete,
        ast.Global,
        ast.Nonlocal,
        ast.ClassDef,
        ast.Lambda,
        ast.Yield,
        ast.YieldFrom,
        ast.Await,
        ast.AsyncFunctionDef,
    )
    _blocked_calls = {
        "compile", "eval", "exec", "__import__", "open", "input", "breakpoint",
        "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr",
    }
    _allowed_builtins = {
        "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "format",
        "frozenset", "int", "len", "list", "map", "max", "min", "print", "range",
        "repr", "reversed", "round", "set", "sorted", "str", "sum", "tuple", "zip",
    }

    def __init__(self, timeout_seconds: float = 5.0, max_output_chars: int = 12_000, max_code_chars: int = 8_000, memory_limit_mb: int = 256) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("Sandbox timeout must be between 0 and 30 seconds")
        if max_output_chars <= 0 or max_output_chars > 100_000:
            raise ValueError("Sandbox output limit must be between 1 and 100,000 characters")
        if max_code_chars <= 0 or max_code_chars > 50_000:
            raise ValueError("Sandbox code limit must be between 1 and 50,000 characters")
        if memory_limit_mb <= 0 or memory_limit_mb > 2_048:
            raise ValueError("Sandbox memory limit must be between 1 and 2,048 MB")
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self.max_code_chars = max_code_chars
        self.memory_limit_mb = memory_limit_mb

    def execute(self, code: str) -> dict[str, object]:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Code cannot be empty")
        if len(code) > self.max_code_chars:
            raise ValueError("Code exceeds the configured sandbox limit")
        self._validate(code)
        wrapper = _build_wrapper(code, self._allowed_builtins)
        with tempfile.TemporaryDirectory(prefix="jarvis-sandbox-") as temp_dir:
            script = Path(temp_dir) / "snippet.py"
            script.write_text(wrapper, encoding="utf-8")
            try:
                kwargs = {
                    "cwd": temp_dir,
                    "env": {"PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1"},
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.PIPE,
                    "text": True,
                    "encoding": "utf-8",
                    "errors": "replace",
                    "timeout": self.timeout_seconds,
                    "check": False,
                }
                if os.name != "nt":
                    kwargs["preexec_fn"] = lambda: _apply_posix_limits(self.memory_limit_mb)
                completed = subprocess.run([sys.executable, "-I", "-S", str(script)], **kwargs)
                result = SandboxResult("completed" if completed.returncode == 0 else "failed", completed.returncode, completed.stdout, completed.stderr, False, False)
            except subprocess.TimeoutExpired as exc:
                result = SandboxResult("timed_out", -1, _decode(exc.stdout), _decode(exc.stderr), True, False)
        stdout, out_truncated = _limit(result.stdout, self.max_output_chars)
        stderr, err_truncated = _limit(result.stderr, self.max_output_chars)
        return SandboxResult(result.status, result.returncode, stdout, stderr, result.timed_out, out_truncated or err_truncated).as_dict()

    def _validate(self, code: str) -> None:
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as exc:
            raise ValueError(f"Code syntax is invalid: {exc.msg}") from exc
        for node in ast.walk(tree):
            if isinstance(node, self._blocked_nodes):
                raise PermissionError(f"Sandbox does not allow {type(node).__name__}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self._blocked_calls:
                    raise PermissionError(f"Sandbox does not allow {node.func.id}()")
                if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("__"):
                    raise PermissionError("Dunder attribute access is blocked")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                raise PermissionError("Dunder names are blocked")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 4_000:
                raise ValueError("String literals are too long")


def _build_wrapper(code: str, allowed_builtins: set[str]) -> str:
    builtin_names = ", ".join(repr(name) for name in sorted(allowed_builtins))
    return textwrap.dedent(
        f"""
        import builtins
        _allowed = {{{builtin_names}}}
        __builtins__ = {{name: getattr(builtins, name) for name in _allowed}}
        del builtins, _allowed
        {code}
        """
    )


def _apply_posix_limits(memory_limit_mb: int) -> None:
    try:
        import resource
        limit = memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))
    except (ImportError, OSError):
        return


def _limit(value: str, limit: int) -> tuple[str, bool]:
    return value[:limit], len(value) > limit


def _decode(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


__all__ = ["CodeSandbox", "SandboxResult"]
