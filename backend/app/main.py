"""Tathabbut API.

Run:  uvicorn app.main:app --reload --port 8000   (from backend/)
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .core import pipeline
from .core.index import HybridIndex
from .schemas import VerifyRequest, VerifyResponse

state: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not (settings.index_dir / "meta.json").exists():
        raise RuntimeError(
            f"Index not found in {settings.index_dir}. Run: python scripts/build_index.py"
        )
    state["index"] = HybridIndex.load(settings.index_dir)
    yield
    state.clear()


app = FastAPI(title="Tathabbut API", version=pipeline.ENGINE_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {
        "name": "Tathabbut API — محرّك تثبّت للتحقق المُسنَد",
        "engine_version": pipeline.ENGINE_VERSION,
        "endpoints": {"verify": "POST /verify", "stats": "GET /index/stats", "docs": "/docs"},
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine_version": pipeline.ENGINE_VERSION}


@app.get("/index/stats")
def index_stats() -> dict:
    return state["index"].stats()


@app.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest) -> dict:
    text = req.text.strip()
    if len(text) > settings.max_input_chars:
        raise HTTPException(413, f"النص أطول من الحد المسموح ({settings.max_input_chars} حرفاً).")
    # No request text is logged or stored (privacy).
    return pipeline.run(state["index"], text, settings.thresholds, settings.quran_link)
