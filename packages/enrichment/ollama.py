from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request

from .noop import NoOpEnricher
from .port import EnrichmentPort


class OllamaEnricher:
    """Optional Ollama client. Falls back to template prose if the daemon is down."""

    def __init__(
        self,
        base_url: str | None = None,
        embed_model: str | None = None,
        chat_model: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip(
            "/"
        )
        self.embed_model = embed_model or os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
        self.chat_model = chat_model or os.getenv("OLLAMA_CHAT_MODEL", "llama3.2")
        self._fallback = NoOpEnricher()
        self.enabled = True

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            return None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            body = self._post("/api/embeddings", {"model": self.embed_model, "prompt": text})
            if not body or "embedding" not in body:
                out.append([])
            else:
                out.append(list(body["embedding"]))
        return out

    def extract_tags(self, title: str, description: str) -> list[str]:
        prompt = (
            "Extract 3-8 short genre/theme tags as a JSON array of strings. "
            f"Title: {title}\nDescription: {description[:1500]}"
        )
        body = self._post(
            "/api/generate",
            {"model": self.chat_model, "prompt": prompt, "stream": False, "format": "json"},
        )
        if not body or "response" not in body:
            return self._fallback.extract_tags(title, description)
        try:
            parsed = json.loads(body["response"])
            if isinstance(parsed, list):
                return [str(x) for x in parsed][:8]
            if isinstance(parsed, dict) and "tags" in parsed:
                return [str(x) for x in parsed["tags"]][:8]
        except json.JSONDecodeError:
            pass
        return []

    def explain_from_factors(
        self,
        item_title: str,
        factors: dict,
        liked_titles: list[str] | None = None,
    ) -> str:
        prompt = (
            "Write one short sentence explaining a media recommendation. "
            "Use only the structured factors; do not invent facts.\n"
            f"Item: {item_title}\nLiked: {liked_titles or []}\nFactors: {json.dumps(factors)}"
        )
        body = self._post(
            "/api/generate",
            {"model": self.chat_model, "prompt": prompt, "stream": False},
        )
        if not body or not body.get("response"):
            return self._fallback.explain_from_factors(item_title, factors, liked_titles)
        return str(body["response"]).strip()

    def summarize_taste(self, preference_blob: dict) -> str:
        prompt = (
            "Summarize this user's media taste in one sentence from the JSON profile.\n"
            f"{json.dumps(preference_blob)[:3000]}"
        )
        body = self._post(
            "/api/generate",
            {"model": self.chat_model, "prompt": prompt, "stream": False},
        )
        if not body or not body.get("response"):
            return self._fallback.summarize_taste(preference_blob)
        return str(body["response"]).strip()


_: EnrichmentPort = OllamaEnricher()  # type: ignore[assignment]
