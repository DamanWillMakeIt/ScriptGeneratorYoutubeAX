"""
BrowseService
─────────────────────────────────────────────────────────────────────────────
Wraps an external browse/research endpoint that takes a search query and
returns scraped content from multiple sites.

ACTIVATION:
    Set in .env:
        ENABLE_BROWSE=true
        BROWSE_ENDPOINT_URL=https://your-endpoint.com/browse
        BROWSE_TIMEOUT_SECONDS=900   ← default 15 min; set lower to fail faster

PIPELINE POSITION:
    Fires AFTER trend hunting, BEFORE script writing.
    Uses the winning topic as the search query.
    Result is appended to the Axigrade writer's context as "web_research".

FAILURE BEHAVIOUR:
    - If disabled   → returns None instantly, pipeline skips it silently
    - If timeout    → logs warning, returns None, pipeline continues normally
    - If HTTP error → logs warning, returns None, pipeline continues normally

This service will never block or crash the main pipeline.
"""

import os
import asyncio
import requests
from typing import Optional


class BrowseService:

    def __init__(self):
        self.enabled      = os.getenv("ENABLE_BROWSE", "false").lower() == "true"
        self.endpoint_url = os.getenv("BROWSE_ENDPOINT_URL", "").strip()
        self.timeout      = int(os.getenv("BROWSE_TIMEOUT_SECONDS", "900"))

        if self.enabled:
            if not self.endpoint_url:
                print("⚠️  BrowseService: ENABLE_BROWSE=true but BROWSE_ENDPOINT_URL is not set. Disabling.")
                self.enabled = False
            else:
                print(f"🌐  BrowseService: ACTIVE | endpoint={self.endpoint_url} | timeout={self.timeout}s")
        else:
            print("🌐  BrowseService: INACTIVE (set ENABLE_BROWSE=true to activate)")

    # ── Public API ────────────────────────────────────────────────────────────

    async def research_topic(self, topic: str) -> Optional[str]:
        """
        Sends `topic` as a search query to the browse endpoint.

        Returns:
            A string of web research content, or None if disabled / failed.
        """
        if not self.enabled:
            return None

        print(f"🌐  BrowseService: researching '{topic}' (timeout={self.timeout}s) ...")

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._call_endpoint(topic),
            )
            if result:
                preview = result[:120].replace("\n", " ")
                print(f"✅  BrowseService: received {len(result)} chars — '{preview}...'")
            return result

        except asyncio.TimeoutError:
            print(f"⚠️  BrowseService: timed out after {self.timeout}s — continuing without web research")
            return None
        except Exception as e:
            print(f"⚠️  BrowseService: unexpected error — {e} — continuing without web research")
            return None

    # ── Internal HTTP call (sync, runs in thread pool) ────────────────────────

    def _call_endpoint(self, query: str) -> Optional[str]:
        """
        POST {query} to the browse endpoint.
        Adjust the request shape below to match your endpoint's contract.
        """
        try:
            response = requests.post(
                self.endpoint_url,
                json={"query": query},          # ← adjust key name if needed
                timeout=self.timeout,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            # Accept both {"result": "..."} and {"content": "..."} and plain strings
            if isinstance(data, str):
                return data
            if isinstance(data, dict):
                return (
                    data.get("result")
                    or data.get("content")
                    or data.get("text")
                    or data.get("summary")
                    or str(data)
                )
            return str(data)

        except requests.Timeout:
            raise asyncio.TimeoutError()
        except requests.HTTPError as e:
            print(f"⚠️  BrowseService HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            print(f"⚠️  BrowseService request error: {e}")
            return None
