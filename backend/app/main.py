import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.db import async_session
from app.models import ScanRun
from app.routes.api import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup, fail any scans left 'running' by a previous process.

    A ScanRun only stays 'running' if the server died mid-scan (BackgroundTasks
    run in-process). Such an orphan would otherwise block every future scan via
    the partial unique index, so sweep it to 'failed' on boot.
    """
    async with async_session() as session:
        await session.execute(
            update(ScanRun)
            .where(ScanRun.status == "running")
            .values(
                status="failed",
                error_message="Server restarted while scan was running",
                completed_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    yield


app = FastAPI(title="MCG Lead Engine API", lifespan=lifespan)

# Allow the frontend origin. Defaults to "*" for local dev; set FRONTEND_ORIGIN
# to the deployed frontend URL in production. (With the Next.js rewrite proxy
# the browser is same-origin, so CORS is effectively unused — this remains for
# any direct cross-origin API access.)
frontend_origin = os.environ.get("FRONTEND_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
