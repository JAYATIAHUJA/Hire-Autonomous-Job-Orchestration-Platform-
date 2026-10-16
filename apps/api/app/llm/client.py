"""Thin wrapper around the Anthropic Messages API. Every LLM call in the app goes here.

What it adds over the bare SDK:
- the model id, effort, timeout and retry budget come from settings, never from call sites;
- structured output through one strict tool (``tool_choice`` stays ``auto``: forcing a
  tool is a 400 on claude-opus-5-5), with a single re-ask if no tool call comes back;
- prompt caching on the system prompt (tools + system form the cached prefix);
- one usage log line per call: account_id, purpose, input/output/cache tokens, cost;
- typed errors for refusals, truncation and transport failures.

Tests never construct ``AnthropicLLMClient`` against the network: they use
``app.llm.fake.FakeLLMClient`` or inject an ``httpx`` mock transport.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import anthropic
import httpx

from ..config import settings

logger = logging.getLogger("hire.llm")

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens: (input, output, cache read, cache write 5m).
PRICES_PER_MTOK: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
}


class LLMError(RuntimeError):
    """The model call failed; nothing it returned may be used."""


class LLMRefusal(LLMError):
    """The model declined the request (stop_reason == "refusal")."""


class LLMTruncated(LLMError):
    """The output hit max_tokens, so the tool input may be incomplete."""


class LLMNoToolCall(LLMError):
    """The model answered without calling the structured-output tool."""


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def cost_usd(self) -> Optional[float]:
        prices = PRICES_PER_MTOK.get(self.model)
        if prices is None:
            return None
        inp, out, read, write = prices
        total = (
            self.input_tokens * inp
            + self.output_tokens * out
            + self.cache_read_input_tokens * read
            + self.cache_creation_input_tokens * write
        )
        return round(total / 1_000_000, 6)


@dataclass(frozen=True)
class ToolCallResult:
    data: dict[str, Any]
    usage: Usage
    request_id: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    def call_tool(
        self,
        *,
        purpose: str,
        account_id: Optional[int],
        system: str,
        content: list[dict[str, Any]],
        tool: dict[str, Any],
    ) -> ToolCallResult:
        """Send one user turn and return the arguments of the model's call to ``tool``."""
        ...


def log_usage(*, purpose: str, account_id: Optional[int], usage: Usage, latency_ms: int,
              request_id: Optional[str]) -> None:
    logger.info(
        "llm_call purpose=%s account_id=%s model=%s input_tokens=%d output_tokens=%d "
        "cache_read_tokens=%d cache_write_tokens=%d cost_usd=%s latency_ms=%d request_id=%s",
        purpose, account_id, usage.model, usage.input_tokens, usage.output_tokens,
        usage.cache_read_input_tokens, usage.cache_creation_input_tokens, usage.cost_usd,
        latency_ms, request_id,
        extra={
            "llm_purpose": purpose,
            "llm_account_id": account_id,
            "llm_model": usage.model,
            "llm_input_tokens": usage.input_tokens,
            "llm_output_tokens": usage.output_tokens,
            "llm_cost_usd": usage.cost_usd,
        },
    )


class AnthropicLLMClient:
    """Production client. One instance per process is fine; the SDK client is thread-safe."""

    def __init__(self, *, api_key: Optional[str] = None, http_client: Optional[httpx.Client] = None):
        kwargs: dict[str, Any] = {
            "timeout": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries,
        }
        key = api_key or settings.anthropic_api_key
        if key:
            kwargs["api_key"] = key
        if http_client is not None:
            kwargs["http_client"] = http_client
        self._client = anthropic.Anthropic(**kwargs)

    def _request(self, system: str, content: list[dict[str, Any]], tool: dict[str, Any]) -> dict[str, Any]:
        extra_body: dict[str, Any] = {"output_config": {"effort": settings.llm_effort}}
        extra_headers: dict[str, str] = {}
        if settings.llm_refusal_fallback:
            extra_body["fallbacks"] = "default"
            extra_headers["anthropic-beta"] = FALLBACK_BETA
        return {
            "model": settings.llm_model,
            "max_tokens": settings.llm_max_tokens,
            # The system prompt is frozen per purpose, so it caches across users and calls.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": [{**tool, "strict": True}],
            "tool_choice": {"type": "auto"},
            "messages": [{"role": "user", "content": content}],
            "extra_body": extra_body,
            "extra_headers": extra_headers,
        }

    def call_tool(self, *, purpose, account_id, system, content, tool) -> ToolCallResult:
        params = self._request(system, content, tool)
        last_error: Optional[LLMError] = None
        # auto tool choice does not guarantee a call; ask once more before giving up.
        for _ in range(2):
            started = time.monotonic()
            try:
                message = self._client.messages.create(**params)
            except anthropic.APIStatusError as exc:
                raise LLMError(f"Anthropic API error {exc.status_code}") from exc
            except anthropic.APIConnectionError as exc:  # includes timeouts
                raise LLMError("Could not reach the Anthropic API") from exc

            raw_usage = getattr(message, "usage", None)
            usage = Usage(
                model=getattr(message, "model", None) or settings.llm_model,
                input_tokens=getattr(raw_usage, "input_tokens", 0) or 0,
                output_tokens=getattr(raw_usage, "output_tokens", 0) or 0,
                cache_read_input_tokens=getattr(raw_usage, "cache_read_input_tokens", 0) or 0,
                cache_creation_input_tokens=getattr(raw_usage, "cache_creation_input_tokens", 0) or 0,
            )
            request_id = getattr(message, "_request_id", None)
            log_usage(purpose=purpose, account_id=account_id, usage=usage,
                      latency_ms=int((time.monotonic() - started) * 1000), request_id=request_id)

            if message.stop_reason == "refusal":
                raise LLMRefusal("The model declined to process this document.")
            if message.stop_reason == "max_tokens":
                raise LLMTruncated("The model output was cut off at max_tokens.")
            for block in message.content:
                if block.type == "tool_use" and block.name == tool["name"]:
                    if not isinstance(block.input, dict):
                        raise LLMError("Tool input was not a JSON object.")
                    return ToolCallResult(data=block.input, usage=usage, request_id=request_id)
            last_error = LLMNoToolCall(f"The model did not call {tool['name']}.")
        raise last_error  # type: ignore[misc]


_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """FastAPI dependency. Tests override it with a fake."""
    global _default_client
    if _default_client is None:
        _default_client = AnthropicLLMClient()
    return _default_client
