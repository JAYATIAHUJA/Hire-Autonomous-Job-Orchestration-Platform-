"""Deterministic stand-in for ``AnthropicLLMClient``, for tests and offline demos."""

from typing import Any, Callable, Optional, Union

from ..config import settings
from .client import ToolCallResult, Usage

Responder = Callable[[dict[str, Any]], dict[str, Any]]


class FakeLLMClient:
    """Returns a canned tool input (or the result of a responder) and records every call."""

    def __init__(self, response: Union[dict[str, Any], Responder, Exception, None] = None):
        self.response = response if response is not None else {}
        self.calls: list[dict[str, Any]] = []

    def call_tool(self, *, purpose: str, account_id: Optional[int], system: str,
                  content: list[dict[str, Any]], tool: dict[str, Any]) -> ToolCallResult:
        call = {"purpose": purpose, "account_id": account_id, "system": system,
                "content": content, "tool": tool}
        self.calls.append(call)
        if isinstance(self.response, Exception):
            raise self.response
        data = self.response(call) if callable(self.response) else self.response
        return ToolCallResult(data=data, usage=Usage(model=settings.llm_model))
