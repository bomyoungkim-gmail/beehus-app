"""
App Console API - FastAPI application entry point.

All domain logic lives in the routers sub-package:
  routers/auth.py        – authentication & JWT
  routers/credentials.py – secure credential management
  routers/users.py       – user management
  routers/downloads.py   – file download & processing
  routers/workspaces.py  – workspace CRUD
  routers/jobs.py        – job CRUD + run trigger / retry
  routers/runs.py        – run listing, detail & stop
  routers/dashboard.py   – dashboard stats & recent runs
  routers/otp.py         – inbox integrations & OTP rules
"""

import asyncio
import json
import logging
import os

import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.db import close_db, init_db
from core.models.mongo_models import Run
from core.services.user_service import ensure_admin_exists
from app.console.websockets import ConnectionManager

# ---------------------------------------------------------------------------
# Import all routers up-front so startup is deterministic and fast
# ---------------------------------------------------------------------------
from app.console.routers import auth, credentials, users, downloads
from app.console.routers import workspaces, jobs, runs, dashboard, otp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WebSocket manager (shared with the Redis listener)
# ---------------------------------------------------------------------------
manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background Redis → WebSocket bridge
# ---------------------------------------------------------------------------

async def _redis_listener():
    """Subscribe to Redis 'run_updates' channel and fan out to WebSocket clients."""
    try:
        r = redis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        await pubsub.subscribe("run_updates")

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                try:
                    payload = json.loads(data)
                    await manager.broadcast(payload)
                except json.JSONDecodeError:
                    logger.warning("Failed to decode Redis message: %s", data)

    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.error("Redis listener error: %s", exc)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

async def lifespan(app: FastAPI):
    """Startup: initialise DB + admin account + Redis listener. Shutdown: clean up."""
    await init_db()
    await ensure_admin_exists()
    redis_task = asyncio.create_task(_redis_listener())

    yield

    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass
    await close_db()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(title="App Console – Beehus Platform", lifespan=lifespan)

# CORS
_extra_origins = os.getenv("CORS_ORIGINS", "")
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
] + [o.strip() for o in _extra_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(auth.router)
app.include_router(credentials.router)
app.include_router(users.router)
app.include_router(downloads.router)
app.include_router(workspaces.router)
app.include_router(jobs.router)
app.include_router(runs.router)
app.include_router(dashboard.router)
app.include_router(otp.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["meta"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "app-console"}


# ---------------------------------------------------------------------------
# Test endpoints (development only)
# ---------------------------------------------------------------------------

@app.post("/test/jpmorgan", tags=["test"])
async def trigger_jpmorgan_test(user: str = "demo_user", password: str = "demo_pass"):
    """Trigger the JPMorgan login task for manual testing."""
    from core.tasks import login_to_jpmorgan_task

    run = Run(job_id="test-job", status="queued", logs=["[System] Manual test triggered"])
    await run.save()

    task = login_to_jpmorgan_task.delay(user, password, str(run.id))
    return {"status": "triggered", "task_id": task.id, "run_id": str(run.id)}


# ---------------------------------------------------------------------------
# WebSocket — real-time run updates
# ---------------------------------------------------------------------------

@app.websocket("/ws/runs")
async def websocket_runs_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; client-to-server messages are not expected
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
