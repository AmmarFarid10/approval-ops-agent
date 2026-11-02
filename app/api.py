import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.auth import authorize
from app.domain import Ledger
from app.workflow import build_graph, ollama_plan


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = os.getenv("DATA_PATH", "data/ops.sqlite3")
    ledger = Ledger(path)
    connection = sqlite3.connect(path + ".checkpoints", check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    app.state.graph = build_graph(
        ledger, saver, ollama_plan if os.getenv("USE_OLLAMA") == "true" else None
    )
    app.state.lock = threading.Lock()
    yield
    connection.close()


app = FastAPI(title="Approval Ops Agent", lifespan=lifespan, dependencies=[Depends(authorize)])


class StartRun(BaseModel):
    order_id: str = Field(pattern=r"^ORD-\d{3}$")
    requested_cents: int = Field(gt=0, le=1_000_000)
    note: str = Field(default="", max_length=2000)


class Decision(BaseModel):
    approved: bool
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def config(run_id: UUID) -> dict:
    return {"configurable": {"thread_id": str(run_id)}, "recursion_limit": 8}


def view(graph, run_id: UUID) -> dict:
    state = graph.get_state(config(run_id))
    if not state.values:
        raise HTTPException(404, "Run not found")
    return {"run_id": str(run_id), "state": state.values, "paused": bool(state.next)}


@app.post("/runs", status_code=201)
def start(body: StartRun, request: Request) -> dict:
    run_id = uuid4()
    with request.app.state.lock:
        request.app.state.graph.invoke(
            {**body.model_dump(), "run_id": str(run_id), "events": []}, config(run_id)
        )
        return view(request.app.state.graph, run_id)


@app.get("/runs/{run_id}")
def get_run(run_id: UUID, request: Request) -> dict:
    with request.app.state.lock:
        return view(request.app.state.graph, run_id)


@app.post("/runs/{run_id}/decision")
def decide(run_id: UUID, body: Decision, request: Request) -> dict:
    with request.app.state.lock:
        current = view(request.app.state.graph, run_id)
        if not current["paused"] or current["state"]["status"] != "awaiting_approval":
            raise HTTPException(409, "Run is not awaiting approval")
        if body.proposal_hash != current["state"]["proposal_hash"]:
            raise HTTPException(409, "Stale proposal hash")
        request.app.state.graph.invoke(Command(resume=body.model_dump()), config(run_id))
        return view(request.app.state.graph, run_id)
