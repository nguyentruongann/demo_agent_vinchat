import hmac
from uuid import uuid4

import redis
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.backend.agents.graph import agent_graph
from src.backend.api.about_routes import router as about_router
from src.backend.api.auth_routes import router as auth_router
from src.backend.api.catalog_routes import router as catalog_router
from src.backend.api.discovery_routes import router as discovery_router
from src.backend.api.faq_routes import router as faq_router
from src.backend.api.promotions_routes import router as promotions_router
from src.backend.api.routes import router as agent_router
from src.backend.api.staff_routes import router as staff_router
from src.backend.api.ticket_routes import router as ticket_router
from src.backend.config import get_settings
from src.backend.models.chat import AskRequest


app = FastAPI(
    title="Vinpearl Multilingual Travel Agent",
    version="0.1.0",
)


def _cors_origins() -> list[str]:
    raw = get_settings().cors_origins
    origins = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]
    return origins or ["http://localhost:5173", "http://127.0.0.1:5173"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(staff_router)
app.include_router(ticket_router)
app.include_router(promotions_router)
app.include_router(catalog_router)
app.include_router(discovery_router)
app.include_router(about_router)
app.include_router(faq_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict[str, str]:
    """Report readiness only when the configured Redis instance is reachable."""
    redis_url = (get_settings().redis_url or "").strip()
    if not redis_url:
        raise HTTPException(status_code=503, detail="REDIS_URL is not configured")

    try:
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
    """Compatibility endpoint protected by ``X-API-Key``."""
    expected_key = (get_settings().agent_api_key or "").strip()
    supplied_key = (x_api_key or "").strip()

    if not expected_key or not supplied_key or not hmac.compare_digest(
        supplied_key,
        expected_key,
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
