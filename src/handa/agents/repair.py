"""One repair, then the file goes to the review queue."""

from pydantic import BaseModel, ValidationError


def accept_schema(payload, schema: type[BaseModel], repair) -> tuple[BaseModel | None, bool]:
    """Return (model, needs_review). needs_review is true only after the repair also fails."""
    try:
        return schema.model_validate(payload), False
    except ValidationError:
        pass
    try:
        return schema.model_validate(repair(payload)), False
    except ValidationError:
        return None, True


def repair_handoff(payload) -> dict:
    if isinstance(payload, str) and payload.strip():
        return {"message": payload.strip()[:400]}
    if isinstance(payload, dict):
        for key in ("message", "text", "summary", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return {"message": value.strip()[:400]}
    return payload
