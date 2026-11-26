"""FastAPI app: POST /ask, GET /api/meta, GET /health, and the static UI."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from . import db, nlu, service  # noqa: E402  (after load_dotenv so env vars are visible)

STATIC = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app):
    if not db.DB_PATH.exists():
        db.build_database()
    yield


app = FastAPI(title="Mini AI BI Assistant", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str


@app.post("/ask")
def ask(req: AskRequest):
    conn = db.connect_readonly()
    try:
        return service.ask(conn, req.question)
    except service.AppError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message)
    finally:
        conn.close()


@app.get("/api/meta")
def meta():
    conn = db.connect_readonly()
    try:
        return {"catalog": db.get_catalog(conn), "rejected_records": db.get_rejected(conn),
                "examples": nlu.EXAMPLES}
    finally:
        conn.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
