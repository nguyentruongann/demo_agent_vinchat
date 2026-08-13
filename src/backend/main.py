import hmac
import os
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from src.backend.api.routes import router
from src.backend.api.auth_routes import router as auth_router
from src.backend.api.staff_routes import router as staff_router
from src.backend.api.ticket_routes import router as ticket_router
from src.backend.api.promotions_routes import router as promotions_router
from src.backend.agents.graph import agent_graph
from src.backend.config import get_settings


app = FastAPI(
    title="Vinpearl Multilingual Travel Agent",
    version="0.1.0",
)


def _cors_origins() -> list[str]:
    raw = get_settings().cors_origins
    origins = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    # Keep a safe local fallback rather than opening production with "*".
    return origins or ["http://localhost:5173", "http://127.0.0.1:5173"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(ticket_router)
app.include_router(promotions_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)


@app.get("/ready")
def ready() -> dict[str, str]:
    """Day 12 / Railway readiness probe.

    Railway should set REDIS_URL from a Redis service. A successful ping means
    this instance is ready to serve public traffic.
    """
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        raise HTTPException(status_code=503, detail="REDIS_URL is not configured")

    try:
        import redis

        client = redis.from_url(
            redis_url,
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
        )
        if not client.ping():
            raise RuntimeError("Redis ping returned false")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis is not ready") from exc

    return {"status": "ready"}


@app.post("/ask")
def ask(
    request: AskRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, str]:
    """Day 12 compatibility endpoint protected by X-API-Key.

    It reuses the project's real LangGraph agent instead of maintaining a
    separate demo agent.
    """
    expected_key = (os.getenv("AGENT_API_KEY") or "").strip()
    supplied_key = (x_api_key or "").strip()

    if not expected_key or not supplied_key or not hmac.compare_digest(
        supplied_key, expected_key
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    session_id = f"CP5-{uuid4().hex}"
    try:
        state = agent_graph.invoke(
            {
                "user_message": request.question,
                "session_id": session_id,
                "user_id": (x_user_id or "anonymous").strip() or "anonymous",
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    answer = str(state.get("answer") or "").strip()
    if not answer:
        raise HTTPException(status_code=500, detail="Agent returned an empty answer")

    return {
        "answer": answer,
        "session_id": str(state.get("session_id") or session_id),
    }

