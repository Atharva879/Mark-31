"""Validated tool registry and execution boundary.

The LLM can request only registered tools. This module never evaluates model
output as Python or passes model-generated text to a shell.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Callable, Mapping

from audit import AuditLogger
from llm.schemas import DispatchResult, RiskTier, ToolSpec
from safety import ConfirmationCallback, build_confirmation_request, requires_confirmation

logger = logging.getLogger(__name__)


class ToolValidationError(ValueError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name or not spec.name.replace("_", "").isalnum():
            raise ValueError("Tool names must be non-empty alphanumeric identifiers")
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolValidationError(f"Unknown tool: {name}") from exc

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())


class Dispatcher:
    def __init__(
        self,
        registry: ToolRegistry,
        audit: AuditLogger,
        confirm: ConfirmationCallback | None = None,
        notify: Callable[[str], None] | None = None,
        max_argument_chars: int = 8_000,
    ) -> None:
        self.registry = registry
        self.audit = audit
        self.confirm = confirm or (lambda _prompt: False)
        self.notify = notify or (lambda message: logger.info(message))
        self.max_argument_chars = max_argument_chars

    def dispatch(self, name: str, arguments: Mapping[str, Any] | None = None) -> DispatchResult:
        spec = self.registry.get(name)
        args = dict(arguments or {})
        self._validate_arguments(spec, args)
        request_id = str(uuid.uuid4())
        self.audit.record(
            "tool_requested",
            request_id=request_id,
            tool_name=name,
            risk=spec.risk.value,
            arguments=args,
        )

        if requires_confirmation(spec):
            request = build_confirmation_request(spec, args)
            approved = bool(self.confirm(request.prompt))
            self.audit.record(
                "confirmation_result",
                request_id=request_id,
                tool_name=name,
                risk=spec.risk.value,
                approved=approved,
            )
            if not approved:
                return DispatchResult(
                    tool_name=name,
                    risk=spec.risk,
                    executed=False,
                    error="User confirmation was not granted",
                    confirmation_required=True,
                )
        elif spec.risk is RiskTier.MODERATE:
            self.notify(f"Executing moderate-risk tool: {name}")

        try:
            output = spec.handler(**args)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:500]}"
            self.audit.record(
                "tool_failed",
                request_id=request_id,
                tool_name=name,
                risk=spec.risk.value,
                error=error,
            )
            return DispatchResult(tool_name=name, risk=spec.risk, executed=True, error=error)

        self.audit.record(
            "tool_completed",
            request_id=request_id,
            tool_name=name,
            risk=spec.risk.value,
            output=output,
        )
        return DispatchResult(tool_name=name, risk=spec.risk, executed=True, output=output)

    def _validate_arguments(self, spec: ToolSpec, arguments: dict[str, Any]) -> None:
        serialized = json.dumps(arguments, ensure_ascii=False, default=str)
        if len(serialized) > self.max_argument_chars:
            raise ToolValidationError("Tool arguments exceed the configured size limit")
        schema = spec.parameters
        if schema.get("type") not in (None, "object"):
            raise ToolValidationError("Tool parameter schema must be an object")
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        missing = required - arguments.keys()
        if missing:
            raise ToolValidationError(f"Missing required arguments: {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            unknown = set(arguments) - set(properties)
            if unknown:
                raise ToolValidationError(f"Unknown arguments: {sorted(unknown)}")
        for key, value in arguments.items():
            if key in properties:
                _validate_value(key, value, properties[key])


def _validate_value(name: str, value: Any, schema: Mapping[str, Any]) -> None:
    expected = schema.get("type")
    valid = {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }
    if expected in valid and not valid[expected]:
        raise ToolValidationError(f"Argument '{name}' must be a {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolValidationError(f"Argument '{name}' must be one of {schema['enum']}")
    if isinstance(value, str) and len(value) > int(schema.get("maxLength", 50_000)):
        raise ToolValidationError(f"Argument '{name}' is too long")


__all__ = ["Dispatcher", "ToolRegistry", "ToolValidationError"]
