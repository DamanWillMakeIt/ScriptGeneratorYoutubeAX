"""
Axigrade Model Router
─────────────────────────────────────────────────────────────────────────────
Routes every AI call to the correct provider via ENV configuration.
Captures real token usage from every API response and logs it to CostTracker.

Per-task model selection (set any / all in your .env):
    DEFAULT_MODEL=gemini
    TREND_HUNTER_MODEL=gemini
    TREND_HUNTER_MODEL_NAME=gemini-2.0-flash
    SCRIPT_WRITER_MODEL=openai
    SCRIPT_WRITER_MODEL_NAME=o3
    PRODUCER_MODEL=claude
    PRODUCER_MODEL_NAME=claude-sonnet-4-5
"""

import os
import asyncio
from typing import Optional
from app.services.cost_tracker import CostTracker


# ── Known task keys ───────────────────────────────────────────────────────────
TASK_ENV_MAP: dict[str, str] = {
    "trend_hunter": "TREND_HUNTER_MODEL",
    "script_writer": "SCRIPT_WRITER_MODEL",
    "producer":      "PRODUCER_MODEL",
}

VALID_PROVIDERS = {"gemini", "openai", "claude"}


class ModelRouter:

    def __init__(self, cost_tracker: Optional[CostTracker] = None):
        self._tracker           = cost_tracker
        self._gemini_available  = False
        self._openai_available  = False
        self._claude_available  = False
        self._openai_client     = None
        self._claude_client     = None
        self._init_clients()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_clients(self):
        gemini_key = os.getenv("GOOGLE_API_KEY")
        if gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                self._gemini_available = True
                print(f"✅ Gemini ready  ({os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')})")
            except ImportError:
                print("⚠️  google-generativeai not installed — Gemini unavailable")

        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                from openai import OpenAI
                self._openai_client    = OpenAI(api_key=openai_key)
                self._openai_available = True
                print(f"✅ OpenAI ready  ({os.getenv('OPENAI_MODEL', 'gpt-4o')})")
            except ImportError:
                print("⚠️  openai not installed — OpenAI unavailable")

        claude_key = os.getenv("ANTHROPIC_API_KEY")
        if claude_key:
            try:
                import anthropic
                self._claude_client    = anthropic.Anthropic(api_key=claude_key)
                self._claude_available = True
                print(f"✅ Claude ready  ({os.getenv('CLAUDE_MODEL', 'claude-opus-4-5')})")
            except ImportError:
                print("⚠️  anthropic not installed — Claude unavailable")

        if not any([self._gemini_available, self._openai_available, self._claude_available]):
            print("🔴 FATAL: No AI provider configured.")

    # ── Routing logic ─────────────────────────────────────────────────────────

    def _resolve_provider(self, task: str) -> str:
        env_key = TASK_ENV_MAP.get(task)
        if env_key:
            val = os.getenv(env_key, "").lower().strip()
            if val in VALID_PROVIDERS:
                return val

        default = os.getenv("DEFAULT_MODEL", "").lower().strip()
        if default in VALID_PROVIDERS:
            return default

        if self._gemini_available:  return "gemini"
        if self._openai_available:  return "openai"
        if self._claude_available:  return "claude"

        raise RuntimeError("No AI model configured.")

    def _resolve_model_name(self, task: str, provider: str) -> str:
        task_env_key = TASK_ENV_MAP.get(task)
        if task_env_key:
            val = os.getenv(task_env_key + "_NAME", "").strip()
            if val:
                return val

        defaults = {
            "gemini": ("GEMINI_MODEL", "gemini-2.0-flash"),
            "openai": ("OPENAI_MODEL", "gpt-4o"),
            "claude": ("CLAUDE_MODEL", "claude-opus-4-5"),
        }
        env_key, fallback = defaults.get(provider, ("", "unknown"))
        return os.getenv(env_key, fallback) if env_key else fallback

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate(
        self,
        prompt:        str,
        task:          str = "default",
        system_prompt: Optional[str] = None,
    ) -> str:
        provider = self._resolve_provider(task)
        print(f"🤖  [{task}] → {provider.upper()}")

        if provider == "gemini":
            return await self._call_gemini(prompt, system_prompt, task)
        elif provider == "openai":
            return await self._call_openai(prompt, system_prompt, task)
        elif provider == "claude":
            return await self._call_claude(prompt, system_prompt, task)
        else:
            raise RuntimeError(f"Unknown provider: {provider}")

    # ── Provider backends ─────────────────────────────────────────────────────

    async def _call_gemini(self, prompt: str, system_prompt: Optional[str], task: str) -> str:
        import google.generativeai as genai

        model_name  = self._resolve_model_name(task, "gemini")
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        print(f"     ↳ gemini model: {model_name}")
        loop  = asyncio.get_event_loop()
        model = genai.GenerativeModel(model_name)
        resp  = await loop.run_in_executor(None, model.generate_content, full_prompt)

        # ── Capture token usage ───────────────────────────────────────────────
        if self._tracker:
            try:
                usage = resp.usage_metadata
                self._tracker.log_llm(
                    task          = task,
                    provider      = "gemini",
                    model         = model_name,
                    input_tokens  = usage.prompt_token_count     or 0,
                    output_tokens = usage.candidates_token_count or 0,
                )
            except Exception:
                pass  # never crash on cost tracking

        return resp.text.strip()

    async def _call_openai(self, prompt: str, system_prompt: Optional[str], task: str) -> str:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        model_name = self._resolve_model_name(task, "openai")
        print(f"     ↳ openai model: {model_name}")

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._openai_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.7,
            ),
        )

        # ── Capture token usage ───────────────────────────────────────────────
        if self._tracker:
            try:
                self._tracker.log_llm(
                    task          = task,
                    provider      = "openai",
                    model         = model_name,
                    input_tokens  = resp.usage.prompt_tokens,
                    output_tokens = resp.usage.completion_tokens,
                )
            except Exception:
                pass

        return resp.choices[0].message.content.strip()

    async def _call_claude(self, prompt: str, system_prompt: Optional[str], task: str) -> str:
        model_name = self._resolve_model_name(task, "claude")
        print(f"     ↳ claude model: {model_name}")

        kwargs: dict = {
            "model":      model_name,
            "max_tokens": 8192,
            "messages":   [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._claude_client.messages.create(**kwargs),
        )

        # ── Capture token usage ───────────────────────────────────────────────
        if self._tracker:
            try:
                self._tracker.log_llm(
                    task          = task,
                    provider      = "claude",
                    model         = model_name,
                    input_tokens  = resp.usage.input_tokens,
                    output_tokens = resp.usage.output_tokens,
                )
            except Exception:
                pass

        return resp.content[0].text.strip()

    # ── Introspection ─────────────────────────────────────────────────────────

    def status(self) -> dict:
        routing = {}
        for task, env_var in TASK_ENV_MAP.items():
            provider = self._resolve_provider(task)
            model    = self._resolve_model_name(task, provider)
            routing[task] = {
                "provider": provider,
                "model":    model,
                "env_key":  env_var,
                "name_key": env_var + "_NAME",
            }
        return {
            "providers_available": {
                "gemini": self._gemini_available,
                "openai": self._openai_available,
                "claude": self._claude_available,
            },
            "task_routing": routing,
        }
