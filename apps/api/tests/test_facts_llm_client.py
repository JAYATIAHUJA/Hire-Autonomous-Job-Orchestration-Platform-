"""The Anthropic wrapper, driven through a mock HTTP transport (no network)."""

import json
import logging

import httpx
import pytest

from app.config import settings
from app.llm.client import AnthropicLLMClient, LLMError, LLMNoToolCall, LLMRefusal, LLMTruncated, Usage

TOOL = {
    "name": "record_things",
    "description": "Record things.",
    "input_schema": {
        "type": "object",
        "properties": {"things": {"type": "array", "items": {"type": "string"}}},
        "required": ["things"],
        "additionalProperties": False,
    },
}


def message(content, stop_reason="tool_use", usage=None):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": settings.llm_model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage or {"input_tokens": 1200, "output_tokens": 300,
                           "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0},
    }


TOOL_USE = {"type": "tool_use", "id": "toolu_1", "name": "record_things", "input": {"things": ["a", "b"]}}


def make_client(responses):
    sent = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append({"headers": dict(request.headers), "body": json.loads(request.content)})
        status, body = queue.pop(0)
        return httpx.Response(status, json=body, headers={"request-id": "req_test"})

    client = AnthropicLLMClient(api_key="test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return client, sent


def call(client):
    return client.call_tool(purpose="test", account_id=7, system="SYSTEM PROMPT",
                            content=[{"type": "text", "text": "hello"}], tool=TOOL)


@pytest.fixture(autouse=True)
def _no_sdk_retries(monkeypatch):
    monkeypatch.setattr(settings, "llm_max_retries", 0)


def test_request_shape_uses_config_model_cached_system_and_strict_tool(caplog):
    client, sent = make_client([(200, message([TOOL_USE]))])
    with caplog.at_level(logging.INFO, logger="hire.llm"):
        result = call(client)

    assert result.data == {"things": ["a", "b"]}
    body = sent[0]["body"]
    assert body["model"] == settings.llm_model
    assert body["system"] == [{"type": "text", "text": "SYSTEM PROMPT", "cache_control": {"type": "ephemeral"}}]
    assert body["tools"][0]["strict"] is True
    assert body["tool_choice"] == {"type": "auto"}  # forced tool choice is a 400 on this model
    assert body["output_config"] == {"effort": settings.llm_effort}
    assert "thinking" not in body and "temperature" not in body
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]

    line = next(r for r in caplog.records if r.name == "hire.llm")
    assert "purpose=test" in line.getMessage() and "account_id=7" in line.getMessage()
    assert line.llm_input_tokens == 1200 and line.llm_output_tokens == 300


def test_model_id_is_only_taken_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "claude-test-override")
    client, sent = make_client([(200, message([TOOL_USE]))])
    call(client)
    assert sent[0]["body"]["model"] == "claude-test-override"


def test_refusal_fallback_can_be_switched_off(monkeypatch):
    client, sent = make_client([(200, message([TOOL_USE]))])
    call(client)
    assert sent[0]["body"]["fallbacks"] == "default"
    assert "server-side-fallback" in sent[0]["headers"]["anthropic-beta"]

    monkeypatch.setattr(settings, "llm_refusal_fallback", False)
    client, sent = make_client([(200, message([TOOL_USE]))])
    call(client)
    assert "fallbacks" not in sent[0]["body"]
    assert "anthropic-beta" not in sent[0]["headers"]


def test_reasks_once_when_no_tool_call_then_gives_up():
    text_only = message([{"type": "text", "text": "Sure!"}], stop_reason="end_turn")
    client, sent = make_client([(200, text_only), (200, message([TOOL_USE]))])
    assert call(client).data == {"things": ["a", "b"]}
    assert len(sent) == 2

    client, sent = make_client([(200, text_only), (200, text_only)])
    with pytest.raises(LLMNoToolCall):
        call(client)


def test_refusal_and_truncation_raise_typed_errors():
    client, _ = make_client([(200, message([], stop_reason="refusal"))])
    with pytest.raises(LLMRefusal):
        call(client)
    client, _ = make_client([(200, message([TOOL_USE], stop_reason="max_tokens"))])
    with pytest.raises(LLMTruncated):
        call(client)


def test_api_errors_are_wrapped():
    client, _ = make_client([(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})])
    with pytest.raises(LLMError):
        call(client)


def test_cost_estimate():
    usage = Usage(model="claude-opus-5-5", input_tokens=1_000_000, output_tokens=100_000)
    assert usage.cost_usd == pytest.approx(4.0 + 2.0)
    assert Usage(model="unknown-model", input_tokens=5).cost_usd is None
