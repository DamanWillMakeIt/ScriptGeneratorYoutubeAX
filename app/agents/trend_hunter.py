"""
TrendHunterAgent — logs all Serper and YouTube API calls to CostTracker.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.services.serper_api import SerperService
from app.services.yt_service import YouTubeService
from app.services.model_router import ModelRouter
from app.services.cost_tracker import CostTracker


class TrendHunterAgent:
    def __init__(self, router: ModelRouter, tracker: Optional[CostTracker] = None):
        self.router  = router
        self.tracker = tracker
        self.serper  = SerperService()
        self.youtube = YouTubeService()

    def _calculate_velocity(self, stats: dict) -> float:
        if not stats:
            return 0.0
        try:
            pub_date    = datetime.strptime(
                stats["published_at"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc)
            hours_alive = max(1.0, (datetime.now(timezone.utc) - pub_date).total_seconds() / 3600)
            return round(stats["view_count"] / hours_alive, 2)
        except Exception as e:
            print(f"Velocity calc error: {e}")
            return 0.0

    def _validate_on_youtube(self, query: str) -> Dict:
        print(f"   → YouTube query: '{query}'")

        # search.list call
        videos = self.youtube.search_videos(query, max_results=5)
        if self.tracker:
            self.tracker.log_service("youtube_search", f"search: {query}",
                                     note="search.list — 100 units")

        total_velocity = 0.0
        valid_count    = 0
        competitors    = []

        for vid in videos:
            stats = self.youtube.get_video_stats(vid["id"])
            # videos.list call
            if self.tracker:
                self.tracker.log_service("youtube_video_stats", f"stats: {vid['id']}",
                                         note="videos.list — 1 unit")
            velocity = self._calculate_velocity(stats)
            if velocity > 0:
                total_velocity += velocity
                valid_count    += 1
                competitors.append(f"https://www.youtube.com/watch?v={vid['id']}")

        score = (total_velocity / valid_count) if valid_count else 0.0
        print(f"     Score (avg VPH): {score:.2f} | competitors: {len(competitors)}")
        return {"score": score, "competitors": competitors[:3]}

    async def find_viral_topic(
        self,
        niche:          str,
        explicit_topic: Optional[str] = None,
    ) -> Dict:
        mode = "EXPLICIT" if explicit_topic else "AUTO"
        print(f"🕵️  TrendHunter [{mode}] | niche='{niche}'"
              + (f" | locked='{explicit_topic}'" if explicit_topic else ""))

        # Step 1: Serper (always)
        raw_signals = self.serper.find_trending_topics(niche) or [
            f"News in {niche}", f"Trending {niche} topics",
        ]
        if self.tracker:
            self.tracker.log_service("serper_search", f"trends: {niche}",
                                     note="Google News past 7 days")
        serper_context = "\n".join(raw_signals[:10])
        print(f"📰  Serper returned {len(raw_signals)} signals")

        # EXPLICIT mode: skip AI brainstorming
        if explicit_topic:
            result = self._validate_on_youtube(explicit_topic)
            return {
                "topic":          explicit_topic,
                "viral_score":    result["score"],
                "competitors":    result["competitors"],
                "serper_context": serper_context,
            }

        # AUTO mode: AI brainstorm → YouTube validation
        prompt = f"""
You are a YouTube Strategist.
Analyze these fresh Google News trends about '{niche}':
{serper_context}

Identify 3 high-potential video angles based on these real signals.
Return a JSON List of objects ONLY.

Format:
[
    {{
        "title": "The Clickbaity Video Title",
        "search_query": "Short Broad Keywords"
    }}
]

Rules:
- "search_query" must be 2-4 words to match MANY YouTube videos
- Base titles on the actual news signals above, not generic ideas
Return ONLY raw JSON — no markdown, no explanation.
"""
        try:
            raw        = await self.router.generate(prompt, task="trend_hunter")
            cleaned    = raw.strip().replace("```json", "").replace("```", "")
            candidates: List[dict] = json.loads(cleaned)
        except Exception as e:
            print(f"⚠️  AI angle error: {e}")
            candidates = [{"title": f"Trends in {niche}", "search_query": niche}]

        print(f"🤖  {len(candidates)} angles suggested. Validating on YouTube...")

        best_topic          = None
        highest_velocity    = -1.0
        winning_competitors: List[str] = []

        for item in candidates:
            title  = item.get("title", niche)
            query  = item.get("search_query", niche)
            result = self._validate_on_youtube(query)

            if result["score"] > highest_velocity:
                highest_velocity    = result["score"]
                best_topic          = title
                winning_competitors = result["competitors"]

        return {
            "topic":          best_topic or niche,
            "viral_score":    highest_velocity,
            "competitors":    winning_competitors,
            "serper_context": serper_context,
        }
