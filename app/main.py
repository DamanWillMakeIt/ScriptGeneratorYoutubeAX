"""
Axigrade API — main FastAPI entry point.
"""

from dotenv import load_dotenv
import os
import uuid
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from app.agents.producer import ProducerAgent
from app.middleware.auth import AuthMiddleware
from app.services.key_store import init_db, generate_key, get_usage, revoke_key
from app.services.job_store import JobStore

load_dotenv()

app = FastAPI(
    title="Axigrade Script Generator API",
    description="AI Pre-Production Architect — viral trend hunting, Axigrade scripting, full cost tracking.",
    version="2.0.0",
)

# ── Middleware (order matters: CORS first, then Auth) ─────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

# ── Init DB on startup ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()

# ── Shared job store ──────────────────────────────────────────────────────────
jobs = JobStore()


# ── Request models ────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    niche:            str           = Field(...,       example="Personal Finance")
    topic:            Optional[str] = Field(None,      example="5 Money Mistakes Killing Your Savings")
    budget:           float         = Field(0.0,       example=50.0, ge=0)
    duration_minutes: float         = Field(1.0,       example=1.0,  gt=0)
    target_language:  str           = Field("English", example="Hindi")

class KeyGenerateRequest(BaseModel):
    user_id: str   = Field(...,              example="user@email.com")
    agent:   str   = Field("youtube-script", example="youtube-script")
    label:   str   = Field("",              example="my-key")
    credits: int   = Field(25,              example=25, gt=0)

class KeyRevokeRequest(BaseModel):
    api_key: str

class AddCreditsRequest(BaseModel):
    api_key: str
    amount:  int = Field(..., example=50, gt=0)


# ── Auth routes (public — no key required) ────────────────────────────────────

@app.post("/api/v1/auth/generate-key", summary="Generate a new API key for a user")
def api_generate_key(body: KeyGenerateRequest):
    """
    One key per user per agent. Returns 409 if key already exists.
    """
    try:
        return generate_key(user_id=body.user_id, agent=body.agent, label=body.label, credits=body.credits)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/v1/auth/usage", summary="Get usage stats for your key")
def api_key_usage(request: Request):
    key  = request.headers.get("X-API-Key", "").strip()
    data = get_usage(key)
    if not data:
        raise HTTPException(status_code=404, detail="Key not found.")
    return data


@app.post("/api/v1/auth/add-credits", summary="Top up credits for a key")
def api_add_credits(body: AddCreditsRequest):
    """Add credits to an existing key. Call this after user pays."""
    from app.services.key_store import add_credits
    result = add_credits(body.api_key, body.amount)
    if not result:
        raise HTTPException(status_code=404, detail="Key not found.")
    return {
        "status":  "credits added",
        "api_key": body.api_key,
        "credits": result["credits"],
    }


@app.get("/api/v1/auth/keys/{user_id}", summary="Get all keys for a user")
def api_user_keys(user_id: str):
    """Frontend calls this to show a user all their keys + usage."""
    from app.services.key_store import get_keys_by_user
    return {"user_id": user_id, "keys": get_keys_by_user(user_id)}


@app.post("/api/v1/auth/revoke", summary="Revoke an API key")
def api_revoke_key(body: KeyRevokeRequest):
    success = revoke_key(body.api_key)
    if not success:
        raise HTTPException(status_code=404, detail="Key not found.")
    return {"status": "revoked", "api_key": body.api_key}


# ── Generate endpoint — async job pattern ─────────────────────────────────────

@app.post("/api/v1/generate", summary="Start a script generation job")
async def generate_video_plan(request: GenerateRequest):
    """
    Returns a job_id immediately. Poll /api/v1/status/{job_id} for results.
    """
    job_id = str(uuid.uuid4())
    jobs.create(job_id)

    async def run_pipeline():
        try:
            jobs.set_running(job_id)
            agent                       = ProducerAgent()
            result_url, project, costs  = await agent.produce_video_plan(
                niche           = request.niche,
                topic           = request.topic,
                budget          = request.budget,
                duration        = request.duration_minutes,
                target_language = request.target_language,
            )
            jobs.set_done(job_id, {
                "status": "success",
                "meta": {
                    "topic":            project.topic,
                    "niche":            project.niche,
                    "language":         project.target_language,
                    "duration_seconds": project.duration_seconds,
                    "total_scenes":     len(project.axigrade_scenes),
                    "total_words":      project.total_word_count,
                    "viral_score_vph":  round(project.viral_score, 2),
                    "competitors":      project.competitor_urls,
                    "pdf_url":          result_url,
                },
                "script": [
                    {
                        "scene_number":           s.scene_number,
                        "estimated_time_seconds": s.estimated_time_seconds,
                        "color_code":             s.color_code,
                        "script_dialogue":        s.script_dialogue,
                        "veo_prompt":             s.veo_prompt,
                        "shoot_instructions":     s.shoot_instructions,
                    }
                    for s in project.axigrade_scenes
                ],
                "cost_breakdown": costs,
            })
        except Exception as e:
            print(f"❌  Pipeline error [{job_id}]: {e}")
            jobs.set_failed(job_id, str(e))

    asyncio.create_task(run_pipeline())

    return {
        "job_id":   job_id,
        "status":   "queued",
        "poll_url": f"/api/v1/status/{job_id}",
        "message":  "Pipeline started. Poll the poll_url every 3-5 seconds for results.",
    }


@app.get("/api/v1/status/{job_id}", summary="Poll job status")
def get_job_status(job_id: str):
    """
    Poll this every 3-5 seconds after calling /generate.

    Possible status values:
      queued  → pipeline hasn't started yet
      running → pipeline is actively running
      done    → result is ready (full script + cost breakdown in response)
      failed  → something went wrong (error message in response)
    """
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


# ── Utility endpoints ─────────────────────────────────────────────────────────

@app.get("/", summary="Health check")
def health_check():
    return {"status": "Axigrade is Online 🏛️", "version": "2.0.0"}


@app.get("/api/v1/models", summary="Show active model routing configuration")
def model_status():
    from app.services.model_router import ModelRouter
    router = ModelRouter()
    return router.status()