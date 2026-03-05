"""
CostTracker
─────────────────────────────────────────────────────────────────────────────
Tracks every LLM token and external service call made during one pipeline run,
then produces a detailed cost breakdown in the final API response.

LLM pricing is based on published per-million-token rates.
External service costs are per-call estimates based on published pricing.

Usage:
    tracker = CostTracker()
    # passed into ModelRouter and every service that needs to log costs
    tracker.log_llm(task, provider, model, input_tokens, output_tokens)
    tracker.log_service(service, operation, units, unit_cost, note)
    breakdown = tracker.summary()
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone


# ── LLM Pricing Table (USD per 1M tokens) ────────────────────────────────────
# Update these if providers change their rates.

LLM_PRICING: dict[str, dict] = {
    # ── Gemini ────────────────────────────────────────────────────────────────
    "gemini-2.0-flash":         {"input": 0.075,  "output": 0.30},
    "gemini-2.0-flash-lite":    {"input": 0.0375, "output": 0.15},
    "gemini-1.5-flash":         {"input": 0.075,  "output": 0.30},
    "gemini-1.5-pro":           {"input": 1.25,   "output": 5.00},
    "gemini-1.0-pro":           {"input": 0.50,   "output": 1.50},

    # ── OpenAI ────────────────────────────────────────────────────────────────
    "gpt-4o":                   {"input": 2.50,   "output": 10.00},
    "gpt-4o-mini":              {"input": 0.15,   "output": 0.60},
    "o3":                       {"input": 10.00,  "output": 40.00},
    "o3-mini":                  {"input": 1.10,   "output": 4.40},
    "o1":                       {"input": 15.00,  "output": 60.00},
    "o1-mini":                  {"input": 3.00,   "output": 12.00},
    "gpt-4-turbo":              {"input": 10.00,  "output": 30.00},

    # ── Anthropic / Claude ────────────────────────────────────────────────────
    "claude-opus-4-5":              {"input": 15.00,  "output": 75.00},
    "claude-sonnet-4-5":            {"input": 3.00,   "output": 15.00},
    "claude-haiku-4-5-20251001":    {"input": 0.80,   "output": 4.00},
    "claude-opus-4-6":              {"input": 15.00,  "output": 75.00},
    "claude-sonnet-4-6":            {"input": 3.00,   "output": 15.00},
}

# Fallback pricing when model not in table (conservative estimate)
UNKNOWN_MODEL_PRICING = {"input": 1.00, "output": 5.00}


# ── External Service Pricing ──────────────────────────────────────────────────

SERVICE_PRICING: dict[str, float] = {
    # Serper: $50 / 50,000 queries = $0.001 per query
    "serper_search":          0.001,

    # YouTube Data API v3: search.list = 100 units, $5 per 1,000 units (after free tier)
    # Simplified: ~$0.0005 per search call
    "youtube_search":         0.0005,

    # YouTube videos.list = 1 unit per call, effectively free
    "youtube_video_stats":    0.000001,

    # Cloudinary: free tier for most use cases; tracked as $0 but logged
    "cloudinary_upload":      0.0,

    # BrowseService: user's own endpoint, cost unknown
    "browse_research":        None,   # None = "external, cost not tracked"
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class LLMCall:
    task:          str
    provider:      str
    model:         str
    input_tokens:  int
    output_tokens: int
    input_cost:    float
    output_cost:   float
    total_cost:    float

@dataclass
class ServiceCall:
    service:    str
    operation:  str
    units:      int
    unit_cost:  Optional[float]
    total_cost: Optional[float]
    note:       str = ""


# ── Main tracker ──────────────────────────────────────────────────────────────

class CostTracker:

    def __init__(self):
        self._llm_calls:     List[LLMCall]     = []
        self._service_calls: List[ServiceCall] = []
        self._started_at     = datetime.now(timezone.utc)

    # ── Logging API ───────────────────────────────────────────────────────────

    def log_llm(
        self,
        task:          str,
        provider:      str,
        model:         str,
        input_tokens:  int,
        output_tokens: int,
    ) -> None:
        pricing    = LLM_PRICING.get(model, UNKNOWN_MODEL_PRICING)
        known      = model in LLM_PRICING

        input_cost  = (input_tokens  / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost  = input_cost + output_cost

        self._llm_calls.append(LLMCall(
            task          = task,
            provider      = provider,
            model         = model + ("" if known else " (est.)"),
            input_tokens  = input_tokens,
            output_tokens = output_tokens,
            input_cost    = round(input_cost,  8),
            output_cost   = round(output_cost, 8),
            total_cost    = round(total_cost,  8),
        ))

    def log_service(
        self,
        service:   str,
        operation: str,
        units:     int  = 1,
        note:      str  = "",
    ) -> None:
        unit_cost  = SERVICE_PRICING.get(service)
        total_cost = (unit_cost * units) if unit_cost is not None else None

        self._service_calls.append(ServiceCall(
            service    = service,
            operation  = operation,
            units      = units,
            unit_cost  = unit_cost,
            total_cost = round(total_cost, 8) if total_cost is not None else None,
            note       = note,
        ))

    # ── Summary ───────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        # ── LLM totals ────────────────────────────────────────────────────────
        total_input_tokens  = sum(c.input_tokens  for c in self._llm_calls)
        total_output_tokens = sum(c.output_tokens for c in self._llm_calls)
        total_llm_cost      = sum(c.total_cost    for c in self._llm_calls)

        # ── Service totals (exclude None = unknown) ───────────────────────────
        known_service_cost = sum(
            c.total_cost for c in self._service_calls if c.total_cost is not None
        )
        unknown_services = [
            c.service for c in self._service_calls if c.total_cost is None
        ]

        grand_total = total_llm_cost + known_service_cost

        return {
            "total_cost_usd": round(grand_total, 6),
            "note": (
                f"Excludes external services with unknown pricing: "
                f"{', '.join(set(unknown_services))}"
                if unknown_services else
                "All costs tracked."
            ),

            "llm": {
                "total_cost_usd":   round(total_llm_cost, 6),
                "total_input_tokens":  total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "calls": [
                    {
                        "task":          c.task,
                        "provider":      c.provider,
                        "model":         c.model,
                        "input_tokens":  c.input_tokens,
                        "output_tokens": c.output_tokens,
                        "cost_usd":      c.total_cost,
                    }
                    for c in self._llm_calls
                ],
            },

            "services": {
                "total_cost_usd": round(known_service_cost, 6),
                "calls": [
                    {
                        "service":    c.service,
                        "operation":  c.operation,
                        "units":      c.units,
                        "cost_usd":   c.total_cost if c.total_cost is not None else "unknown (external)",
                        "note":       c.note,
                    }
                    for c in self._service_calls
                ],
            },
        }
