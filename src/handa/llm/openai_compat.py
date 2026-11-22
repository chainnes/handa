"""OpenAI-compatible chat. Works with OpenAI, Groq, OpenRouter, Ollama, and LM Studio."""

import json
import logging
import time

import httpx

from handa.config import Settings
from handa.errors import ProviderError
from handa.llm.base import Completion, ToolCall
from handa.logging_setup import redact

log = logging.getLogger("handa.llm")


class OpenAIModel:
    provider = "openai"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.llm_model
        if not settings.llm_api_key.strip():
            raise ProviderError(
                "HANDA_LLM_API_KEY is empty. Set it in .env, or leave HANDA_LLM_PROVIDER=mock."
            )
        self.url = settings.llm_base_url.rstrip("/") + "/chat/completions"

    def complete(self, *, agent: str, messages: list[dict], tools: list[dict] | None = None) -> Completion:
        payload = {
            "model": self.settings.llm_model,
            "temperature": 0.1,
            "max_tokens": 800,
            "messages": _wire(messages),
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return _parse(self._post(payload))

    def _post(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}", "Content-Type": "application/json"}
        last = "The model provider did not answer."
        for attempt in range(3):
            try:
                response = httpx.post(self.url, headers=headers, json=payload, timeout=self.settings.llm_timeout_s)
            except httpx.TimeoutException:
                last = "The model provider timed out."
                log.warning("llm timeout attempt=%s", attempt + 1)
                time.sleep(0.4 * (attempt + 1))
                continue
            except httpx.HTTPError as exc:
                last = "The model provider could not be reached."
                log.warning("llm transport %s", redact(str(exc), self.settings.llm_api_key))
                time.sleep(0.4 * (attempt + 1))
                continue
            if response.status_code == 401:
                raise ProviderError("The model provider rejected the API key.")
            if response.status_code == 400 and "temperature" in payload:
                payload = {key: value for key, value in payload.items() if key != "temperature"}
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                last = f"The model provider returned HTTP {response.status_code}."
                log.warning(
                    "llm status=%s body=%s",
                    response.status_code,
                    redact(response.text, self.settings.llm_api_key),
                )
                time.sleep(0.5 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise ProviderError(
                    f"The model provider returned HTTP {response.status_code}. "
                    + redact(response.text, self.settings.llm_api_key)
                )
            return response.json()
        raise ProviderError(last)


def _wire(messages: list[dict]) -> list[dict]:
    wired = []
    for message in messages:
        if message.get("role") == "tool":
            wired.append(
                {
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id") or message.get("name"),
                    "name": message.get("name"),
                    "content": message.get("content") or "",
                }
            )
            continue
        row = {"role": message.get("role") or "user", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            row["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])},
                }
                for call in message["tool_calls"]
            ]
        wired.append(row)
    return wired


def _parse(body: dict) -> Completion:
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("The model provider returned an unexpected payload.") from exc
    calls = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function") or {}
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                parsed = {}
        else:
            parsed = arguments or {}
        calls.append(
            ToolCall(
                id=raw.get("id") or function.get("name") or "call",
                name=function.get("name") or "",
                arguments=parsed,
            )
        )
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return Completion(content=content, tool_calls=calls)
