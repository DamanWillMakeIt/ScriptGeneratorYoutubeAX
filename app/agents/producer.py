"""
ProducerAgent — full pipeline orchestrator.

Pipeline:
  Phase 1 · Discovery     → TrendHunterAgent (Serper + YouTube VPH)
  Phase 2 · Web Research  → BrowseService (feature-flagged)
  Phase 3 · Transcript    → ScriptFetcher
  Phase 4 · Planning      → Blueprint generation
  Phase 5 · Execution     → ScriptWriterAgent / Axigrade
  Phase 6 · Publishing    → PDFService + UploadService

Returns: (pdf_url, project, cost_breakdown)
"""

import json
import os
from typing import Optional, Tuple

from app.agents.trend_hunter import TrendHunterAgent
from app.agents.script_writer import ScriptWriterAgent
from app.services.script_fetcher import ScriptFetcher
from app.services.budget_calc import BudgetService
from app.services.pdf_gen import PDFService
from app.services.upload_service import UploadService
from app.services.model_router import ModelRouter
from app.services.browse_service import BrowseService
from app.services.cost_tracker import CostTracker
from app.schemas.project import VideoProject, SceneBlueprint


class ProducerAgent:
    def __init__(self):
        self.tracker        = CostTracker()
        self.router         = ModelRouter(cost_tracker=self.tracker)
        self.trend_agent    = TrendHunterAgent(router=self.router, tracker=self.tracker)
        self.writer_agent   = ScriptWriterAgent(router=self.router)
        self.fetcher        = ScriptFetcher()
        self.budget_service = BudgetService()
        self.pdf_service    = PDFService()
        self.upload_service = UploadService()
        self.browse_service = BrowseService()

    # ── Main pipeline ─────────────────────────────────────────────────────────

    async def produce_video_plan(
        self,
        niche:           str,
        budget:          float,
        duration:        float,
        target_language: str = "English",
        topic:           Optional[str] = None,
    ) -> Tuple[str, VideoProject, dict]:
        duration_seconds = int(duration * 60)

        print(
            f"🎬  PRODUCER START | niche={niche} | budget=${budget} | "
            f"{duration_seconds}s | lang={target_language}"
            + (f" | explicit_topic='{topic}'" if topic else "")
        )

        # ── Phase 1: Discovery ────────────────────────────────────────────────
        trend_data     = await self.trend_agent.find_viral_topic(
            niche          = niche,
            explicit_topic = topic,
        )
        final_topic    = trend_data["topic"]
        competitors    = trend_data["competitors"]
        serper_context = trend_data.get("serper_context", "")
        viral_score    = trend_data.get("viral_score", 0)
        print(f"✅  Final topic: '{final_topic}' | VPH score: {viral_score:.1f}")

        # ── Phase 2: Web Research (feature-flagged) ───────────────────────────
        web_research: Optional[str] = None
        if self.browse_service.enabled:
            print(f"🌐  Launching BrowseService for: '{final_topic}'")
            web_research = await self.browse_service.research_topic(final_topic)
            self.tracker.log_service("browse_research", f"research: {final_topic}",
                                     note="External endpoint — cost not tracked")
        else:
            print("🌐  BrowseService inactive — skipping")

        # ── Phase 3: Competitor Transcript ────────────────────────────────────
        reference_script = ""
        if competitors:
            print(f"👀  Fetching transcript: {competitors[0]}")
            try:
                fetched = self.fetcher.fetch_transcript(competitors[0])
                if fetched:
                    reference_script = fetched[:5000]
                    print(f"✅  Transcript fetched ({len(reference_script)} chars)")
                else:
                    print("⚠️  Transcript unavailable")
            except Exception as e:
                print(f"⚠️  Transcript error: {e}")

        # ── Phase 4: Planning ─────────────────────────────────────────────────
        project = VideoProject(
            topic            = final_topic,
            niche            = niche,
            budget_limit     = budget,
            target_duration  = duration,
            duration_seconds = duration_seconds,
            target_language  = target_language,
            competitor_urls  = competitors,
            reference_script = reference_script,
            serper_context   = serper_context,
            web_research     = web_research or "",
            viral_score      = viral_score,
        )
        project.budget_plan = self.budget_service.calculate_budget(budget)
        project.blueprint   = await self._generate_blueprint(project)

        # ── Phase 5: Execution (Axigrade) ─────────────────────────────────────
        print(f"✍️   Axigrade Writer ({len(project.blueprint)} scenes)...")
        project = await self.writer_agent.generate_script(project)

        # ── Phase 6: Publishing ───────────────────────────────────────────────
        print("🖨️   Generating PDF...")
        safe_name  = "".join(c if c.isalnum() else "_" for c in final_topic)[:30]
        filename   = f"script_{safe_name}.pdf"
        local_path = self.pdf_service.create_shooting_script(project, filename=filename)

        public_url = self.upload_service.upload_pdf(local_path, filename)
        self.tracker.log_service("cloudinary_upload", f"upload: {filename}",
                                 note="PDF upload to Cloudinary")

        if public_url and os.path.exists(local_path):
            os.remove(local_path)
            print("🧹  Local file cleaned up.")

        cost_breakdown = self.tracker.summary()
        print(f"💰  Total estimated cost: ${cost_breakdown['total_cost_usd']}")

        return (public_url or local_path), project, cost_breakdown

    # ── Blueprint generation ──────────────────────────────────────────────────

    def _extract_json_list(self, text: str) -> str:
        start = text.find("[")
        end   = text.rfind("]") + 1
        return text[start:end] if start != -1 and end > 0 else text

    async def _generate_blueprint(self, project: VideoProject) -> list[SceneBlueprint]:
        """
        Scene count formula:
          1 scene per ~25 seconds of video (proper YouTube pacing)
          Minimum 5, no artificial cap.

          Examples:
            60s  →  ~5  scenes
            2min →  ~8  scenes
            5min →  ~18 scenes
            10min → ~28 scenes
        """
        target_scenes = max(5, round(project.duration_seconds / 25))

        # Build a human-readable structure guide for the AI
        structure_guide = self._structure_guide(target_scenes, project.duration_seconds)

        prompt = f"""
You are a YouTube Producer. Plan a detailed video structure for:
  Topic    : {project.topic}
  Duration : {project.target_duration} minutes ({project.duration_seconds} seconds)
  Budget   : ${project.budget_limit}

Competitor Script Reference:
{(project.reference_script or "")[:800]}

TASK: Create EXACTLY {target_scenes} scenes. No more, no less.

Suggested structure:
{structure_guide}

Rules:
- Scene durations must add up to exactly {project.duration_seconds} seconds
- Every scene must have a distinct goal — no filler, no repetition
- Distribute pacing: mix Green (hook/energy), Yellow (content), Red (only if unavoidable)

Output a JSON List ONLY (no markdown, no explanation):
[
    {{
        "scene_number": 1,
        "section_type": "Hook",
        "goal": "Stop the scroll in 3 seconds with a shocking stat",
        "visual_style": "Extreme close-up face cam, snap zoom",
        "duration_sec": 10
    }}
]
"""
        try:
            raw       = await self.router.generate(prompt, task="producer")
            cleaned   = raw.strip().replace("```json", "").replace("```", "")
            json_text = self._extract_json_list(cleaned)
            data      = json.loads(json_text)
            blueprint = [SceneBlueprint(**item) for item in data]

            # Warn if AI disobeyed the count
            if len(blueprint) != target_scenes:
                print(f"⚠️  Blueprint: requested {target_scenes} scenes, got {len(blueprint)}")

            print(f"📋  Blueprint: {len(blueprint)} scenes for {project.duration_seconds}s video")
            return blueprint
        except Exception as e:
            print(f"⚠️  Blueprint error: {e}")
            return [SceneBlueprint(scene_number=1, section_type="Hook",
                                   goal="Intro", visual_style="Face cam", duration_sec=30)]

    def _structure_guide(self, total_scenes: int, duration_seconds: int) -> str:
        """
        Generates a proportional structure hint so the AI
        knows how to distribute scene types across the video.
        """
        avg_sec = duration_seconds // total_scenes

        # Proportional allocation
        hook_scenes    = max(1, round(total_scenes * 0.07))   # ~7%
        intro_scenes   = max(1, round(total_scenes * 0.10))   # ~10%
        content_scenes = max(1, round(total_scenes * 0.60))   # ~60%
        story_scenes   = max(1, round(total_scenes * 0.13))   # ~13%
        cta_scenes     = max(1, round(total_scenes * 0.10))   # ~10%

        return (
            f"  - {hook_scenes}x  Hook         (~{avg_sec}s each) — scroll-stopping opener\n"
            f"  - {intro_scenes}x  Intro/Setup  (~{avg_sec}s each) — establish the problem/promise\n"
            f"  - {content_scenes}x  Main Content (~{avg_sec}s each) — core value, tips, explanation\n"
            f"  - {story_scenes}x  Story/Proof  (~{avg_sec}s each) — examples, case studies, data\n"
            f"  - {cta_scenes}x  CTA/Outro    (~{avg_sec}s each) — subscribe, link, loopable ending"
        )
