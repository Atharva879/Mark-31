"""Safety-first local command execution without shell interpretation."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    executable: str
    arguments: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "executable": self.executable,
            "arguments": list(self.arguments),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "truncated": self.truncated,
        }


class SafeCommandExecutor:
    _BLOCKED_ARGUMENTS = {"-c", "--command", "-command", "-encodedcommand", "--eval", "-e", "exec", "eval", "&", "|", ";", ">", "<"}

    def __init__(
        self,
        allowed_executables: set[str],
        allowed_working_roots: tuple[Path, ...] = (),
        timeout_seconds: float = 15.0,
        max_output_chars: int = 12_000,
    ) -> None:
        if not allowed_executables:
            raise ValueError("At least one shell executable must be allowlisted")
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError("Shell timeout must be between 0 and 120 seconds")
        if max_output_chars <= 0 or max_output_chars > 100_000:
            raise ValueError("Shell output limit must be between 1 and 100,000 characters")
        self.allowed_executables = frozenset(item.strip().lower() for item in allowed_executables if item.strip())
        self.allowed_working_roots = tuple(root.expanduser().resolve() for root in allowed_working_roots)
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    def execute(self, command: str, working_directory: str | None = None) -> dict[str, object]:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Command cannot be empty")
        if len(command) > 2_000:
            raise ValueError("Command exceeds the 2,000-character limit")
        try:
            argv = shlex.split(command, posix=os.name != "nt")
        except ValueError as exc:
            raise ValueError("Command quoting is invalid") from exc
        if not argv:
            raise ValueError("Command cannot be empty")
        executable = Path(argv[0]).name.lower()
        if argv[0] != executable and Path(argv[0]).name != argv[0]:
            raise PermissionError("Executable paths are not accepted; use an allowlisted executable name")
        if executable not in self.allowed_executables:
            raise PermissionError(f"Executable '{executable}' is not allowlisted")
        resolved = shutil.which(argv[0])
        if resolved is None:
            raise FileNotFoundError(f"Allowlisted executable was not found: {argv[0]}")
        if len(argv) > 41:
            raise ValueError("Command may contain at most 40 arguments")
        if any(argument.lower() in self._BLOCKED_ARGUMENTS for argument in argv[1:]):
            raise PermissionError("Interpreter evaluation and command chaining arguments are blocked")
        if any(len(argument) > 1_000 for argument in argv[1:]):
            raise ValueError("Command arguments are too long")
        cwd = self._working_directory(working_directory)
        try:
            completed = subprocess.run(
                [resolved, *argv[1:]],
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
            timed_out = False
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _decode_output(exc.stdout)
            stderr = _decode_output(exc.stderr)
            returncode = -1
        stdout, stdout_truncated = _limit(stdout, self.max_output_chars)
        stderr, stderr_truncated = _limit(stderr, self.max_output_chars)
        return CommandResult(
            executable=executable,
            arguments=tuple(argv[1:]),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            truncated=stdout_truncated or stderr_truncated,
        ).as_dict()

    def _working_directory(self, value: str | None) -> Path:
        if value is None or not value.strip():
            return Path.cwd().resolve()
        candidate = Path(value).expanduser().resolve()
        roots = self.allowed_working_roots or (Path.cwd().resolve(),)
        if not any(candidate == root or root in candidate.parents for root in roots):
            raise PermissionError("Working directory is outside the configured allowed roots")
        if not candidate.is_dir():
            raise NotADirectoryError(str(candidate))
        return candidate


def _limit(value: str | bytes | None, limit: int) -> tuple[str, bool]:
    text = _decode_output(value)
    return text[:limit], len(text) > limit


def _decode_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


__all__ = ["CommandResult", "SafeCommandExecutor"]
