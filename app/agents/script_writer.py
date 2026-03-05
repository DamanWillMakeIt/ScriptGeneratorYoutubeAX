"""
Axigrade ScriptWriterAgent
──────────────────────────────────────────────────────────────────────────────
Generates the full scene-by-scene script in one AI call.
Critically: the blueprint from ProducerAgent is passed in explicitly
so the AI cannot collapse or skip scenes.
"""

import json
from app.schemas.project import VideoProject, AxigradeScene, SceneBlueprint
from app.services.model_router import ModelRouter

AXIGRADE_SYSTEM_PROMPT = """
Role: Act as an elite Pre-Production Architect and Expert JSON Developer.

Objective: Generate a highly engaging, scene-by-scene video script formatted
STRICTLY as a JSON object. The script must perfectly align with the user's
requested duration, budget, language, and topic.

Core Directives & Constraints:

1. Strict Topic & Language Adherence:
   - Topic: Stick strictly to the user's requested topic.
   - Language: `script_dialogue` MUST be written natively in the user's requested
     `target_language`. Use native idioms, natural phrasing, culturally relevant hooks.
     (Note: `color_code`, `veo_prompt`, `shoot_instructions` must remain in English.)

2. Duration & Word Count Physics (CRITICAL):
   - Assume a pacing of 2.5 words per second (150 WPM).
   - Each scene's `script_dialogue` word count must match its `estimated_time_seconds`.
     Formula: words = estimated_time_seconds × 2.5
   - Example: a 30s scene must have ~75 words of dialogue. Not 10. Not 200.

3. Budget-Aware Production:
   - Low Budget ($0–$50): simple visuals — talking head, text overlays, basic B-roll.
   - High Budget ($50+): cinematic — drone shots, snap zooms, elaborate scenes.

4. Script Quality & Pacing:
   - Scene 1: hard hook — stops a scroller within 3 seconds.
   - Dialogue: native, concise, zero fluff. No essay writing.
   - Final scene: precise CTA or loopable ending.

5. Strict JSON Output Schema:
   Return ONLY valid JSON. No markdown. No introductory text.
   Output MUST be an object with a `scenes` array. Each scene MUST include:
   - `scene_number`           : integer
   - `estimated_time_seconds` : integer  ← must match the blueprint value exactly
   - `script_dialogue`        : string   ← in target_language, word count = time × 2.5
   - `veo_prompt`             : string   ← English only
   - `shoot_instructions`     : string   ← English only
   - `color_code`             : "Green" | "Yellow" | "Red"
"""


class ScriptWriterAgent:
    def __init__(self, router: ModelRouter):
        self.router = router

    async def generate_script(self, project: VideoProject) -> VideoProject:
        required_scenes = len(project.blueprint)
        max_words       = int(project.duration_seconds * 2.5)
        budget_tier     = "Low Budget ($0–$50)" if project.budget_limit <= 50 else f"High Budget (${project.budget_limit})"

        print(
            f"✍️  Axigrade Writer | topic={project.topic} | "
            f"{project.duration_seconds}s | {required_scenes} scenes required | "
            f"lang={project.target_language} | budget=${project.budget_limit}"
        )

        # ── Serialise blueprint so AI knows EXACTLY what to write ────────────
        blueprint_text = self._format_blueprint(project.blueprint)

        # ── Research context ──────────────────────────────────────────────────
        context_sections = []
        if project.serper_context:
            context_sections.append(
                f"TRENDING NEWS SIGNALS (Google, past 7 days):\n{project.serper_context[:600]}"
            )
        if project.web_research:
            context_sections.append(
                f"DEEP WEB RESEARCH:\n{project.web_research[:1500]}"
            )
        if project.reference_script:
            context_sections.append(
                f"COMPETITOR TRANSCRIPT (style reference):\n{project.reference_script[:800]}"
            )
        context_block = ""
        if context_sections:
            context_block = "\nRESEARCH CONTEXT (use this to make the script accurate and timely):\n"
            context_block += "\n\n".join(context_sections)

        prompt = f"""
Generate a complete YouTube video script using the Axigrade system.

VIDEO BRIEF:
  Topic             : {project.topic}
  Niche             : {project.niche}
  Target Language   : {project.target_language}
  Duration          : {project.duration_seconds} seconds
  Budget Tier       : {budget_tier}
  Max Total Words   : {max_words} words across ALL scenes combined
{context_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCENE BLUEPRINT — YOU MUST WRITE EXACTLY {required_scenes} SCENES.
DO NOT merge, skip, or add scenes. Follow this structure precisely:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{blueprint_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CRITICAL RULES:
1. Output EXACTLY {required_scenes} scenes — one per blueprint entry above.
2. Each scene's `estimated_time_seconds` must match the blueprint value exactly.
3. Each scene's `script_dialogue` word count must equal estimated_time_seconds × 2.5.
4. `script_dialogue` must be in {project.target_language} (native, NOT translated English).
5. `veo_prompt` and `shoot_instructions` must be in English.
6. Scene 1 = hard hook (stops scroll in 3 seconds).
7. Final scene = CTA or loopable ending.

Return ONLY a valid JSON object:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "estimated_time_seconds": 10,
      "script_dialogue": "...",
      "veo_prompt": "...",
      "shoot_instructions": "...",
      "color_code": "Green"
    }}
  ]
}}
"""

        raw = await self.router.generate(
            prompt=prompt,
            task="script_writer",
            system_prompt=AXIGRADE_SYSTEM_PROMPT,
        )

        scenes = self._parse_axigrade_response(raw, project, required_scenes)

        # ── Enforce standard: retry once if AI returned fewer scenes ─────────
        if len(scenes) < required_scenes:
            print(
                f"🔁  Scene count {len(scenes)} < required {required_scenes}. "
                f"Retrying with stricter enforcement..."
            )
            existing_scenes_text = "\n".join(
                f"  Scene {s.scene_number} already written: {s.script_dialogue[:60]}..."
                for s in scenes
            )
            retry_prompt = f"""
RETRY — YOUR PREVIOUS RESPONSE WAS REJECTED.

You returned {len(scenes)} scenes. The standard requires EXACTLY {required_scenes} scenes.
This is non-negotiable. A 10-minute video needs {required_scenes} scenes. A 1-minute video
needs {required_scenes} scenes. Do not collapse. Do not merge. Do not skip.

{prompt}

ADDITIONALLY: You already wrote these scenes — continue FROM scene {len(scenes)+1}
and write the FULL script again with ALL {required_scenes} scenes.
"""
            raw2   = await self.router.generate(
                prompt=retry_prompt,
                task="script_writer",
                system_prompt=AXIGRADE_SYSTEM_PROMPT,
            )
            scenes = self._parse_axigrade_response(raw2, project, required_scenes)

            if len(scenes) < required_scenes:
                print(f"⚠️  Retry still returned {len(scenes)} scenes. Accepting best result.")

        project.axigrade_scenes = scenes
        return project

    # ── Blueprint formatter ───────────────────────────────────────────────────

    def _format_blueprint(self, blueprint: list[SceneBlueprint]) -> str:
        lines = []
        for b in blueprint:
            lines.append(
                f"  Scene {b.scene_number:>2} | {b.duration_sec:>3}s | "
                f"{b.section_type:<18} | Goal: {b.goal}"
            )
        total = sum(b.duration_sec for b in blueprint)
        lines.append(f"  {'─'*70}")
        lines.append(f"  Total: {total}s across {len(blueprint)} scenes")
        return "\n".join(lines)

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_axigrade_response(
        self, raw: str, project: VideoProject, required_scenes: int
    ) -> list[AxigradeScene]:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[1]
                cleaned = cleaned.lstrip("json").strip().rstrip("`").strip()

            data   = json.loads(cleaned)
            scenes = data.get("scenes", data) if isinstance(data, dict) else data

            result = []
            for item in scenes:
                cc = item.get("color_code", "Yellow")
                if cc not in ("Green", "Yellow", "Red"):
                    cc = "Yellow"
                result.append(AxigradeScene(
                    scene_number           = int(item.get("scene_number", len(result) + 1)),
                    estimated_time_seconds = int(item.get("estimated_time_seconds", 10)),
                    script_dialogue        = str(item.get("script_dialogue", "")),
                    veo_prompt             = str(item.get("veo_prompt", "")),
                    shoot_instructions     = str(item.get("shoot_instructions", "")),
                    color_code             = cc,
                ))

            total_words = sum(len(s.script_dialogue.split()) for s in result)
            expected    = int(project.duration_seconds * 2.5)

            if len(result) != required_scenes:
                print(f"⚠️  Scene count mismatch: expected {required_scenes}, got {len(result)}")
            else:
                print(f"✅  Axigrade: {len(result)} scenes | {total_words} words / {expected} max")

            return result

        except Exception as e:
            print(f"⚠️  Axigrade parse error: {e}\nRaw:\n{raw[:400]}")
            return self._fallback_scene(project)

    def _fallback_scene(self, project: VideoProject) -> list[AxigradeScene]:
        return [AxigradeScene(
            scene_number=1,
            estimated_time_seconds=project.duration_seconds,
            script_dialogue="[Script generation failed — please retry]",
            veo_prompt="Talking head on plain background.",
            shoot_instructions="Static camera, centre frame.",
            color_code="Red",
        )]
