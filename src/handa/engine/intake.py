"""Turn free text into an EventRequest. Missing fields are a list, not a guess."""

from __future__ import annotations

from datetime import date, timedelta
import re

from handa.schemas import EventRequest

REQUIRED = ("event_type", "guests", "event_date", "event_time", "city", "budget_php")
QUESTIONS = {
    "event_type": "Is this a corporate lunch, a debut, a wedding, or a fiesta?",
    "guests": "How many guests?",
    "event_date": "What date? You can say today, tomorrow, or in 21 days.",
    "event_time": "What time does service start? Use 24-hour HH:MM.",
    "city": "Which city is the venue in?",
    "budget_php": "What is the budget in pesos?",
}
_CITIES = ("Quezon City", "Taguig", "Antipolo", "Tagaytay")
_TYPES = (
    ("wedding", "wedding"),
    ("debut", "debut"),
    ("fiesta", "fiesta"),
    ("corporate", "corporate"),
    ("lunch", "corporate"),
    ("office", "corporate"),
)


def parse_request(text: str, today: date | None = None) -> EventRequest:
    today = today or date.today()
    raw = " ".join(text.split())
    event = EventRequest(raw_text=text.strip(), notes="")
    guests = re.search(r"(\d+)\s*(guests|guest|pax|people|persons)\b", raw, re.I)
    if guests:
        event.guests = int(guests.group(1))
    veg = re.search(r"(\d+)\s*vegetarian", raw, re.I)
    if veg:
        event.vegetarian_guests = int(veg.group(1))
    budget = re.search(r"budget(?:\s+of|\s+is|:)?\s*₱?\s*([\d,]+)", raw, re.I)
    if budget:
        event.budget_php = float(budget.group(1).replace(",", ""))
    clock = re.search(r"\b(?:at\s+)?(\d{1,2}:\d{2})\b", raw)
    if clock:
        event.event_time = _clock(clock.group(1))
    event.event_date = _date(raw, today)
    for name, kind in _TYPES:
        if re.search(rf"\b{name}\b", raw, re.I):
            event.event_type = kind  # type: ignore[assignment]
            break
    for city in _CITIES:
        if city.lower() in raw.lower():
            event.city = city
            break
    if re.search(r"\bno pork\b", raw, re.I):
        event.exclude.append("pork")
    if re.search(r"\bno beef\b", raw, re.I):
        event.exclude.append("beef")
    if re.search(r"\bno seafood\b|\bno fish\b", raw, re.I):
        event.exclude.append("seafood")
    client = re.match(r"(.+?)\s+(?:needs|wants)\b", raw, re.I)
    if client:
        event.client_name = client.group(1).strip()
    venue = re.search(r"\bat\s+([A-Z][^.]{3,60}?)(?:\.|$)", text.strip())
    if venue and not re.match(r"\d{1,2}:\d{2}", venue.group(1)):
        event.venue = venue.group(1).strip()
    if event.event_name is None and event.event_type:
        event.event_name = f"{event.event_type.title()} service"
    return event


def missing_fields(event: EventRequest) -> list[str]:
    missing = []
    for field in REQUIRED:
        if getattr(event, field) in (None, "", []):
            missing.append(field)
    if event.guests is not None and event.vegetarian_guests > event.guests:
        missing.append("vegetarian_guests")
    return missing


def questions_for(missing: list[str]) -> list[str]:
    return [QUESTIONS.get(field, field) for field in missing if field in QUESTIONS]


def apply_answer(event: EventRequest, answer, today: date | None = None) -> EventRequest:
    today = today or date.today()
    data = event.model_dump()
    if isinstance(answer, dict):
        for key, value in answer.items():
            if value not in (None, ""):
                data[key] = value
        return EventRequest.model_validate(data)
    text = str(answer).strip()
    parsed = parse_request(text, today)
    for field in (*REQUIRED, "client_name", "venue", "vegetarian_guests", "event_name"):
        current = data.get(field)
        incoming = getattr(parsed, field)
        if current in (None, "", []) and incoming not in (None, "", []):
            data[field] = incoming
    if data.get("budget_php") is None and re.fullmatch(r"₱?\s*[\d,]+(?:\.\d+)?", text):
        data["budget_php"] = float(text.replace("₱", "").replace(",", "").strip())
    if data.get("guests") is None and re.fullmatch(r"\d+", text):
        data["guests"] = int(text)
    for rule in parsed.exclude:
        if rule not in data["exclude"]:
            data["exclude"].append(rule)
    return EventRequest.model_validate(data)


def _clock(value: str) -> str | None:
    hour, minute = (int(part) for part in value.split(":"))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _date(text: str, today: date) -> date | None:
    if re.search(r"\btoday\b", text, re.I):
        return today
    if re.search(r"\btomorrow\b", text, re.I):
        return today + timedelta(days=1)
    relative = re.search(r"\bin\s+(\d+)\s+days?\b", text, re.I)
    if relative:
        return today + timedelta(days=int(relative.group(1)))
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return date.fromisoformat(iso.group(1))
    return None
