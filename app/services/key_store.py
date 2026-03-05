"""
KeyStore — MongoDB backend.
Database   : axigrade
Collection : api_keys

Document schema:
{
  key:          "axg_...",        # unique API key
  user_id:      "user@email.com", # from frontend (email or their user ID)
  label:        "my-key",         # optional friendly name
  credits:      100,              # 1 credit = 1 pipeline run
  call_count:   0,                # total lifetime calls
  created_at:   "...",
  last_used_at: "...",
  is_active:    true
}
"""

import secrets
import os
from datetime import datetime, timezone
from typing import Optional
from pymongo import MongoClient, DESCENDING
from pymongo.collection import Collection

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
_client: Optional[MongoClient] = None


def _col() -> Collection:
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client["axigrade"]["api_keys"]


def init_db() -> None:
    col = _col()
    col.create_index("key", unique=True)
    col.create_index("user_id")
    col.create_index([("user_id", 1), ("agent", 1)], unique=True)
    print("✅  KeyStore (MongoDB) initialised → axigrade.api_keys")


def generate_key(user_id: str, agent: str = "youtube-script", label: str = "", credits: int = 25) -> dict:
    """
    One key per user per agent. Raises ValueError if already exists.
    user_id = email or unique ID from frontend.
    agent   = which agent this key is for (e.g. "youtube-script", "seo", "thumbnail")
    """
    existing = _col().find_one({"user_id": user_id, "agent": agent}, {"_id": 0})
    if existing:
        raise ValueError(f"Key already exists for user '{user_id}' on agent '{agent}'.")

    key = "axg_" + secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "key":          key,
        "user_id":      user_id,
        "agent":        agent,
        "label":        label,
        "credits":      credits,
        "call_count":   0,
        "created_at":   now,
        "last_used_at": None,
        "is_active":    True,
    }
    _col().insert_one(doc)
    return {
        "api_key":    key,
        "user_id":    user_id,
        "agent":      agent,
        "credits":    credits,
        "created_at": now,
    }


def validate_key(key: str) -> Optional[dict]:
    """Returns key doc if valid and active, None otherwise."""
    return _col().find_one({"key": key, "is_active": True}, {"_id": 0})


def deduct_credit(key: str) -> bool:
    """
    Atomically deduct 1 credit. Returns True if successful.
    Returns False if credits already 0 (don't run pipeline).
    """
    result = _col().find_one_and_update(
        {"key": key, "credits": {"$gt": 0}},
        {"$inc": {"credits": -1}},
        projection={"_id": 0}
    )
    return result is not None


def log_usage(key: str) -> None:
    """Increment call_count and update last_used_at."""
    now = datetime.now(timezone.utc).isoformat()
    _col().update_one(
        {"key": key},
        {"$inc": {"call_count": 1}, "$set": {"last_used_at": now}}
    )


def add_credits(key: str, amount: int) -> Optional[dict]:
    """Top up credits for a key. Returns updated doc."""
    result = _col().find_one_and_update(
        {"key": key},
        {"$inc": {"credits": amount}},
        return_document=True,
        projection={"_id": 0}
    )
    return result


def get_usage(key: str) -> Optional[dict]:
    return _col().find_one({"key": key}, {"_id": 0})


def get_keys_by_user(user_id: str) -> list[dict]:
    """Get all keys for a user_id."""
    return list(_col().find({"user_id": user_id}, {"_id": 0}))


def revoke_key(key: str) -> bool:
    result = _col().update_one({"key": key}, {"$set": {"is_active": False}})
    return result.matched_count > 0


def list_keys() -> list[dict]:
    return list(_col().find({}, {"_id": 0}).sort("created_at", DESCENDING))