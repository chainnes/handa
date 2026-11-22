"""One agent turn: tool calls, then one schema repair, then the review queue."""

import json
import logging
import re

from pydantic import ValidationError

log = logging.getLogger("handa.agents")


def run_agent(*, agent: str, model, tools: dict, schema, user: str, system: str, max_steps: int = 6):
    """Return (parsed or None, tool records, needs_review)."""
    specs = [_spec(name, fn) for name, fn in tools.items()]
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    records = []
    repaired = False
    for _step in range(max_steps):
        completion = model.complete(agent=agent, messages=messages, tools=specs or None)
        if completion.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": completion.content or "",
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in completion.tool_calls
                    ],
                }
            )
            for call in completion.tool_calls:
                result = _call(tools, call.name, call.arguments)
                records.append({"name": call.name, "arguments": call.arguments, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "tool_call_id": call.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            continue
        try:
            parsed = schema.model_validate(_object(completion.content))
            return parsed, records, False
        except (ValidationError, ValueError) as exc:
            log.info("schema miss agent=%s repaired=%s", agent, repaired)
            if repaired:
                return None, records, True
            repaired = True
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "That did not match the schema. Reply with one JSON object only. "
                        f"Validation error: {exc}"
                    ),
                }
            )
    return None, records, True


def _call(tools: dict, name: str, arguments: dict) -> dict:
    fn = tools.get(name)
    if fn is None:
        return {"ok": False, "error": f"Unknown tool {name}."}
    try:
        result = fn(arguments or {})
        if isinstance(result, dict):
            return result
        return {"ok": True, "result": result}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _object(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no json object")
    return json.loads(text[start : end + 1])


def _spec(name: str, fn) -> dict:
    schema = getattr(fn, "tool_schema", None) or {"type": "object", "properties": {}}
    description = getattr(fn, "tool_description", "") or name
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": schema},
    }
