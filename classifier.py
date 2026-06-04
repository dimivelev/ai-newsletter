"""Provider-agnostic classifier — supports Anthropic Claude, OpenAI, Ollama, or NVIDIA NIM.

Pick the provider in config.yaml:

    provider: anthropic        # or "openai", "ollama", "nim"
    models:
      anthropic: claude-haiku-4-5-20251001
      openai:    gpt-5-mini
      nim:       meta/llama-3.1-70b-instruct

Set the matching key in `.env`:

    ANTHROPIC_API_KEY=sk-ant-...
    OPENAI_API_KEY=sk-proj-...
    NVIDIA_API_KEY=nvapi-...

Each batch returns a JSON array of {topic, importance, why, tldr}.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Sequence

from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an AI news triage analyst. For each item you receive,
output a JSON object with:
  "topic": one of {topics}
  "importance": 1 (routine), 2 (notable), 3 (major)
  "why": <= 15 words explaining the importance score
  "tldr": <= 25-word plain-English summary for a busy exec

Expected distribution: roughly 60% routine, 30% notable, 10% major.
Be willing to assign 2 and 3 — this is a high-signal AI news feed, not general news.

Importance guidelines:
 - 3 (major) — new model release, major funding round ($100M+), new regulation/law,
       breakthrough result, company acquisition, safety incident, major product launch.
 - 2 (notable) — product update, research paper release, partnership announcement,
       policy proposal, opinion from a major figure, funding round, benchmark result,
       new feature from a major company, interesting analysis.
 - 1 (routine) — minor blog post, incremental update, speculative article, personal
       milestone, content that is mostly noise in an AI context.

Return ONLY a JSON array, one object per input item, in the same order."""


def _build_user_prompt(items: Sequence[dict], topics: list[str]) -> str:
    lines = []
    for i, it in enumerate(items):
        lines.append(
            f"[{i}] source={it['source']} | title={it['title']} | "
            f"summary={(it.get('summary') or '')[:400]}"
        )
    topic_list = " | ".join(topics)
    return (
        f"Allowed topics: {topic_list}\n\n"
        f"Classify these {len(items)} items:\n\n" + "\n".join(lines)
    )


def _parse_response(text: str) -> list[dict]:
    """Strip code fences if present, then parse JSON array."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1].rsplit("\n", 1)[0]
        if text.startswith("json"):
            text = text[4:].lstrip()
    parsed = json.loads(text)
    # Some models wrap the array in {"items": [...]} or {"results": [...]}
    if isinstance(parsed, dict):
        for key in ("items", "results", "classifications", "data"):
            if key in parsed and isinstance(parsed[key], list):
                return parsed[key]
        # Single item dict — wrap in list
        return [parsed]
    return parsed


# ─── Provider interface ──────────────────────────────────────────────────

class BaseClassifier(ABC):
    """Provider-agnostic classifier interface."""

    @abstractmethod
    def _call(self, system: str, user: str) -> str:
        """Call the LLM and return the raw response text."""
        ...

    def generate_response(self, system: str, user: str) -> str:
        return self._call(system, user)

    def classify_batch(self, items: Sequence[dict], topics: list[str],
                       batch_size: int = 10) -> list[dict]:
        results: list[dict] = []
        system = SYSTEM_PROMPT.format(topics=", ".join(topics))
        for i in range(0, len(items), batch_size):
            chunk = items[i:i + batch_size]
            user = _build_user_prompt(chunk, topics)
            try:
                text = self._call(system, user)
                parsed = _parse_response(text)
                if len(parsed) != len(chunk):
                    log.warning("Batch %d: expected %d results, got %d",
                                i, len(chunk), len(parsed))
                results.extend(parsed[:len(chunk)])
                while len(results) < i + len(chunk):
                    results.append(self._fallback("classification truncated"))
            except Exception as e:
                log.exception("Classify batch %d failed: %s", i, e)
                for _ in chunk:
                    results.append(self._fallback("classifier error"))
        return results

    @staticmethod
    def _fallback(why: str) -> dict:
        return {"topic": "Applications", "importance": 1, "why": why, "tldr": ""}


# ─── Anthropic (Claude) ──────────────────────────────────────────────────

class AnthropicClassifier(BaseClassifier):
    def __init__(self, model: str, api_key: str | None = None) -> None:
        from anthropic import Anthropic
        self.model = model
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=2, min=2, max=30))
    def _call(self, system: str, user: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text


# ─── OpenAI ──────────────────────────────────────────────────────────────

class OpenAIClassifier(BaseClassifier):
    def __init__(self, model: str, api_key: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai"
            ) from e
        self.model = model
        self.client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=2, min=2, max=30))
    def _call(self, system: str, user: str) -> str:
        # response_format={"type": "json_object"} forces valid JSON.
        # The model wraps in {"items": [...]}; _parse_response unwraps it.
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system",
                 "content": system + "\n\nWrap the JSON array in {\"items\": [...]}"},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


# ─── Ollama (local LLM via Ollama's OpenAI-compatible API) ──────────────

class OllamaClassifier(OpenAIClassifier):
    """Local Ollama instance — fully free, no paid API key required.

    Install Ollama from https://ollama.com, run `ollama pull llama3.2`
    (or any other model), and point this classifier at the default port.
    """

    def __init__(self, model: str, base_url: str = "http://localhost:11434/v1") -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package is required for the Ollama provider. "
                "Run: pip install openai"
            ) from e
        self.model = model
        # api_key is ignored by Ollama but required by the OpenAI SDK.
        self.client = OpenAI(api_key="ollama", base_url=base_url)

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=2, min=2, max=30))
    def _call(self, system: str, user: str) -> str:
        # Many Ollama models don't support response_format=json_object;
        # rely on the prompt to force JSON.
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


# ─── NVIDIA NIM (OpenAI-compatible API) ──────────────────────────────────

class NIMClassifier(OpenAIClassifier):
    """NVIDIA NIM API — OpenAI-compatible endpoints for high-performance inference.
    
    Requires NVIDIA_API_KEY set in your environment.
    """

    def __init__(self, model: str, api_key: str | None = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(
                "openai package is required for the NIM provider. "
                "Run: pip install openai"
            ) from e
        self.model = model
        key = api_key or os.environ.get("NVIDIA_API_KEY")
        if not key:
            raise RuntimeError("NVIDIA_API_KEY not set in env / .env")
        self.client = OpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1")

    @retry(stop=stop_after_attempt(3),
           wait=wait_exponential(multiplier=2, min=2, max=30))
    def _call(self, system: str, user: str) -> str:
        # Many NIM models may not cleanly support response_format=json_object 
        # in the exact same way as OpenAI, so rely on prompt to force JSON.
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""


# ─── Factory ─────────────────────────────────────────────────────────────

def get_classifier(cfg: dict) -> BaseClassifier:
    """Build a classifier based on config.

    Expected config keys:
        provider: 'anthropic' | 'openai' | 'ollama' | 'nim'
        models:
          anthropic: <model name>
          openai:    <model name>
          nim:       <model name>

    Falls back to legacy `classifier_model` when no `models` block exists.
    """
    provider = (cfg.get("provider") or "anthropic").lower()
    models = cfg.get("models") or {}
    model = models.get(provider) or cfg.get("classifier_model")

    if not model:
        raise RuntimeError(
            f"No model configured for provider '{provider}'. "
            f"Set models.{provider} in config.yaml."
        )

    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set in env / .env")
        return AnthropicClassifier(model)

    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY not set in env / .env")
        return OpenAIClassifier(model)

    if provider == "ollama":
        base_url = cfg.get("ollama_base_url", "http://localhost:11434/v1")
        return OllamaClassifier(model, base_url=base_url)

    if provider == "nim":
        return NIMClassifier(model)

    raise ValueError(
        f"Unknown provider '{provider}'. Supported: anthropic, openai, ollama, nim."
    )


# ─── Backwards-compat shim ───────────────────────────────────────────────

def classify_batch(items, topics, model, batch_size: int = 10):
    """Legacy API — kept so old callers don't break.

    Newer code should use `get_classifier(cfg).classify_batch(items, topics)`.
    """
    log.warning("classify_batch() top-level function is deprecated; "
                "use get_classifier(cfg).classify_batch() instead.")
    clf = AnthropicClassifier(model)
    return clf.classify_batch(items, topics, batch_size=batch_size)
