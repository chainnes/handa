"""HTTP desk. The page, the run stream, and the API live in one process."""

from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from handa import __version__
from handa.config import get_settings
from handa.errors import DeskError
from handa.logging_setup import setup_logging
from handa.sample_data.generate import generate_catalog
from handa.service import Desk

STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("handa.api")


class RunBody(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ReplyBody(BaseModel):
    answer: dict | str


class DisruptionBody(BaseModel):
    kind: str


class DecisionBody(BaseModel):
    action: str
    notes: str = ""


def create_app(desk: Desk | None = None) -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    holder: dict = {"desk": desk}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if holder["desk"] is None:
            holder["desk"] = Desk.create(settings)
        yield

    app = FastAPI(title="Handa", version=__version__, lifespan=lifespan)

    def current() -> Desk:
        if holder["desk"] is None:
            holder["desk"] = Desk.create(settings)
        return holder["desk"]

    @app.get("/api/health")
    def health():
        office = current()
        return {
            "status": "ok",
            "version": __version__,
            "provider": office.settings.provider_label,
            "embeddings": office.settings.embeddings,
            "documents": office.index.count(),
            "recipes": len(office.catalog["recipes"]),
            "suppliers": len(office.catalog["suppliers"]),
            "currency": "PHP",
        }

    @app.get("/api/requests")
    def requests():
        return generate_catalog()["requests"]

    @app.post("/api/runs")
    def start_run(body: RunBody):
        run_id = current().begin(body.text)
        return {"run_id": run_id}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return current().view(run_id)

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str):
        office = current()

        def stream():
            for event in office.iter_events(run_id):
                yield f"data: {json.dumps(event, default=str)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/runs/{run_id}/reply")
    def reply(run_id: str, body: ReplyBody):
        current().reply(run_id, body.answer)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/disruption")
    def disruption(run_id: str, body: DisruptionBody):
        current().disrupt(run_id, body.kind)
        return {"ok": True}

    @app.post("/api/runs/{run_id}/decision")
    def decision(run_id: str, body: DecisionBody):
        return current().decide(run_id, body.action, body.notes)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

    @app.exception_handler(DeskError)
    async def desk_error(_request: Request, exc: DeskError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        return JSONResponse(status_code=422, content={"error": first.get("msg", "The request is not valid.")})

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"error": "The desk hit an unexpected error."})

    return app
