"""
JobStore — MongoDB backed.
Jobs persist across workers, restarts, and Render spin-downs.

Collection: axigrade.jobs
"""

import os
from datetime import datetime, timezone
from typing import Optional
from pymongo import MongoClient, DESCENDING

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
_client = None


def _col():
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client["axigrade"]["jobs"]


def init_jobs_db():
    col = _col()
    col.create_index("job_id", unique=True)
    col.create_index("created_at")
    print("✅  JobStore (MongoDB) initialised → axigrade.jobs")


class JobStore:

    def create(self, job_id: str) -> dict:
        job = {
            "job_id":     job_id,
            "status":     "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "result":     None,
            "error":      None,
        }
        _col().insert_one({**job})
        return job

    def set_running(self, job_id: str):
        _col().update_one(
            {"job_id": job_id},
            {"$set": {"status": "running", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

    def set_done(self, job_id: str, result: dict):
        _col().update_one(
            {"job_id": job_id},
            {"$set": {"status": "done", "result": result, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

    def set_failed(self, job_id: str, error: str):
        _col().update_one(
            {"job_id": job_id},
            {"$set": {"status": "failed", "error": error, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

    def get(self, job_id: str) -> Optional[dict]:
        doc = _col().find_one({"job_id": job_id}, {"_id": 0})
        return doc
