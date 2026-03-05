from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# ── 1. BUDGET & FINANCE ───────────────────────────────────────────────────────

class CostItem(BaseModel):
    item: str             = Field(..., description="Expense name")
    estimated_cost: float = Field(..., description="Cost in USD")
    category: str         = Field(..., description="Visual, Audio, Location, or Software")
    is_essential: bool    = True

class BudgetPlan(BaseModel):
    total_budget:    float
    currency:        str            = "USD"
    breakdown:       List[CostItem] = []
    recommendations: List[str]      = Field(..., description="Cost-saving tips")


# ── 2. SCENE ARCHITECTURE (blueprint phase) ───────────────────────────────────

class SceneBlueprint(BaseModel):
    scene_number:  int
    section_type:  str
    goal:          str = Field(..., description="Retention goal")
    visual_style:  str = Field(..., description="Visual direction based on budget")
    duration_sec:  int


# ── 3. AXIGRADE SCENE — final output schema ───────────────────────────────────

class AxigradeScene(BaseModel):
    scene_number:           int
    estimated_time_seconds: int
    script_dialogue:        str = Field(..., description="Spoken words in target_language")
    veo_prompt:             str = Field(..., description="AI video generation prompt (English)")
    shoot_instructions:     str = Field(..., description="Directorial cues (English)")
    color_code:             Literal["Green", "Yellow", "Red"]

    @property
    def word_count(self) -> int:
        return len(self.script_dialogue.split())

    @property
    def expected_words(self) -> int:
        return int(self.estimated_time_seconds * 2.5)


# ── 4. THE MASTER PROJECT OBJECT ──────────────────────────────────────────────

class VideoProject(BaseModel):
    # ── User Input ────────────────────────────────────────────────────────────
    topic:            str
    niche:            str
    budget_limit:     float
    target_duration:  float = 1.0
    duration_seconds: int   = 60
    target_language:  str   = "English"

    # ── Research context (populated by TrendHunterAgent + BrowseService) ──────
    competitor_urls:  List[str]      = []
    reference_script: Optional[str] = ""
    serper_context:   str            = ""
    web_research:     str            = ""
    viral_score:      float          = 0.0  # avg Views Per Hour of winning topic

    # ── Planning ──────────────────────────────────────────────────────────────
    blueprint:   List[SceneBlueprint] = []
    budget_plan: Optional[BudgetPlan] = None

    # ── Axigrade Execution ────────────────────────────────────────────────────
    axigrade_scenes: List[AxigradeScene] = []

    # ── Legacy compat ─────────────────────────────────────────────────────────
    final_script: List = []

    @property
    def total_word_count(self) -> int:
        return sum(len(s.script_dialogue.split()) for s in self.axigrade_scenes)

    @property
    def total_scene_duration(self) -> int:
        return sum(s.estimated_time_seconds for s in self.axigrade_scenes)
