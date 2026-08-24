"""Safety primitives for risk classification and irreversible-action confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from llm.schemas import RiskTier, ToolSpec


ConfirmationCallback = Callable[[str], bool]


@dataclass(frozen=True)
class ConfirmationRequest:
    tool_name: str
    risk: RiskTier
    arguments: dict
    prompt: str


def requires_confirmation(spec: ToolSpec) -> bool:
    return spec.risk is RiskTier.SENSITIVE or spec.confirmation_required


def build_confirmation_request(spec: ToolSpec, arguments: dict) -> ConfirmationRequest:
    rendered = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    prompt = (
        f"Confirm SENSITIVE action '{spec.name}'"
        f" ({spec.description}). Arguments: {rendered or 'none'}."
    )
    return ConfirmationRequest(spec.name, spec.risk, arguments, prompt)


__all__ = ["ConfirmationCallback", "ConfirmationRequest", "build_confirmation_request", "requires_confirmation"]
