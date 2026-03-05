"""
JobStore
─────────────────────────────────────────────────────────────────────────────
In-memory store for async pipeline jobs.
Each job has a status: queued → running → done | failed

Jobs are kept in memory — they reset on server restart.
For production persistence, swap the dict for Redis or SQLite.
"""

from datetime import datetime, timezone
from typing import Optional


class JobStore:

    def __init__(self):
        self._jobs: dict[str, dict] = {}

    def create(self, job_id: str) -> dict:
        job = {
            "job_id":     job_id,
            "status":     "queued",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "result":     None,
            "error":      None,
        }
        self._jobs[job_id] = job
        return job

    def set_running(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id]["status"]     = "running"
            self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def set_done(self, job_id: str, result: dict):
        if job_id in self._jobs:
            self._jobs[job_id]["status"]     = "done"
            self._jobs[job_id]["result"]     = result
            self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def set_failed(self, job_id: str, error: str):
        if job_id in self._jobs:
            self._jobs[job_id]["status"]     = "failed"
            self._jobs[job_id]["error"]      = error
            self._jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def get(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)
