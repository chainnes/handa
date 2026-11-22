"""Schemas the desk will accept or refuse. Money is only trusted after the cost engine fills it."""

from datetime import date
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EventType = Literal["corporate", "debut", "wedding", "fiesta"]
ServiceStyle = Literal["dropoff", "buffet", "plated"]
Exclusion = Literal["pork", "beef", "seafood"]
QuoteStatus = Literal["draft", "issued", "issued_exception", "cancelled", "changes_requested"]
BudgetStatus = Literal["pass", "revise", "fail"]


class EventBrief(BaseModel):
    client_name: str = Field(min_length=1, max_length=120)
    event_name: str = Field(min_length=1, max_length=160)
    event_type: EventType
    service_style: ServiceStyle | None = None
    pax: int = Field(ge=8, le=800)
    event_date: date
    service_time: str = "12:00"
    venue: str = Field(min_length=1, max_length=180)
    city: str = Field(min_length=1, max_length=80)
    budget_php: float = Field(gt=0, le=5_000_000)
    exclude: list[Exclusion] = Field(default_factory=list)
    vegetarian_pax: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=1000)

    @field_validator("exclude")
    @classmethod
    def unique_exclusions(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return seen

    @field_validator("service_time")
    @classmethod
    def clock(cls, value: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("service_time must be HH:MM using 24-hour time")
        return value

    @model_validator(mode="after")
    def dates_and_plates(self) -> "EventBrief":
        if self.vegetarian_pax > self.pax:
            raise ValueError("vegetarian_pax cannot be larger than pax")
        if self.event_date < date.today():
            raise ValueError("event_date is in the past")
        return self


class Citation(BaseModel):
    source: str
    title: str
    excerpt: str
    score: float = 0


class PortionLine(BaseModel):
    dish_id: str
    name: str
    course: str
    portions: int = Field(ge=0)
    diet_tags: list[str]
    allergens: list[str]
    unit_cost_php: float = Field(ge=0)
    line_cost_php: float = Field(ge=0)
    note: str = ""


class MenuPlan(BaseModel):
    service_style: ServiceStyle
    revision: int = Field(ge=0)
    lines: list[PortionLine]
    food_cost_php: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""
    citations: list[Citation] = Field(default_factory=list)


class PurchaseLine(BaseModel):
    item: str
    qty: float = Field(ge=0)
    unit: str
    supplier: str
    unit_price_php: float = Field(ge=0)
    est_cost_php: float = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    late: bool = False


class ProcurementPlan(BaseModel):
    lines: list[PurchaseLine]
    food_cost_php: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""
    citations: list[Citation] = Field(default_factory=list)


class BudgetAudit(BaseModel):
    food_php: float
    service_php: float
    equipment_php: float
    travel_php: float
    overhead_php: float
    cost_php: float
    quote_php: float
    budget_php: float
    gap_php: float
    margin_rate: float
    floor_margin: float
    margin_at_budget: float
    status: BudgetStatus
    guidance: str
    rationale: str = ""
    citations: list[Citation] = Field(default_factory=list)


class CrewMember(BaseModel):
    role: str
    count: int = Field(ge=0)
    call_time: str
    notes: str = ""


class TimelineItem(BaseModel):
    when: str
    what: str


class LogisticsPlan(BaseModel):
    crew: list[CrewMember]
    timeline: list[TimelineItem]
    equipment_notes: list[str]
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""
    citations: list[Citation] = Field(default_factory=list)


class QuoteLine(BaseModel):
    label: str
    amount_php: float


class Quotation(BaseModel):
    number: str
    status: QuoteStatus
    client_name: str
    event_name: str
    event_date: str
    pax: int
    service_style: ServiceStyle
    package_php: float = Field(ge=0)
    per_head_php: float = Field(ge=0)
    cost_lines: list[QuoteLine]
    total_php: float = Field(ge=0)
    cost_php: float = Field(ge=0)
    margin_rate: float
    menu_lines: list[PortionLine]
    assumptions: list[str]
    client_note: str
    warnings: list[str] = Field(default_factory=list)
    manager_notes: str = ""
    citations: list[Citation] = Field(default_factory=list)


class Narrative(BaseModel):
    rationale: str = Field(min_length=8, max_length=800)


class SupervisorDecision(BaseModel):
    next_agent: Literal["menu", "logistics"]
    reason: str = Field(min_length=8, max_length=600)


class HumanDecision(BaseModel):
    action: Literal["approve", "approve_exception", "revise", "cancel"]
    notes: str = Field(default="", max_length=500)


class TraceEvent(BaseModel):
    agent: str
    kind: Literal["tool", "result", "guardrail", "note", "error"]
    title: str
    summary: str
    tone: Literal["info", "ok", "warn", "bad"] = "info"


class RunView(BaseModel):
    run_id: str
    status: str
    event: EventBrief
    revision: int
    trace: list[TraceEvent]
    menu: MenuPlan | None = None
    procurement: ProcurementPlan | None = None
    budget: BudgetAudit | None = None
    logistics: LogisticsPlan | None = None
    quotation: Quotation | None = None
    pending: dict | None = None
    error: str | None = None


class SampleBrief(BaseModel):
    id: str
    label: str
    blurb: str
    event: dict


class EventRequest(BaseModel):
    """Partial on purpose. Intake interrupts until the required fields exist."""

    client_name: str | None = None
    event_name: str | None = None
    event_type: EventType | None = None
    guests: int | None = Field(default=None, ge=8, le=800)
    event_date: date | None = None
    event_time: str | None = None
    venue: str | None = None
    city: str | None = None
    budget_php: float | None = Field(default=None, gt=0, le=5_000_000)
    exclude: list[Exclusion] = Field(default_factory=list)
    vegetarian_guests: int = Field(default=0, ge=0)
    notes: str = ""
    raw_text: str = ""

    @field_validator("event_time")
    @classmethod
    def clock(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("event_time must be HH:MM")
        return value

    @field_validator("exclude")
    @classmethod
    def unique_exclusions(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return seen


class AgentMessage(BaseModel):
    id: str
    from_agent: str
    to_agent: str
    summary: str
    tone: Literal["info", "ok", "warn", "bad"] = "info"
    source: Literal["llm", "tool", "python"] = "python"
    model: str = ""


class Handoff(BaseModel):
    message: str = Field(min_length=8, max_length=400)


class IntakeNote(BaseModel):
    note: str = Field(min_length=8, max_length=400)
    follow_up: str = Field(default="", max_length=400)


class MenuChoice(BaseModel):
    recipe_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=8, max_length=500)
    swaps: list[str] = Field(default_factory=list)


class QuoteSummary(BaseModel):
    summary: str = Field(min_length=8, max_length=500)
