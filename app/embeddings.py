from __future__ import annotations

import hashlib
import os
from typing import List

import google.generativeai as genai
import numpy as np


class EmbeddingService:
    def __init__(self, model: str = "models/text-embedding-004"):
        self.model = model
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.use_remote = bool(self.api_key)
        if self.use_remote:
            genai.configure(api_key=self.api_key)

    def _fallback_embed(self, text: str, dim: int = 384) -> list[float]:
        if not text:
            return [0.0] * dim
        vec = np.zeros(dim, dtype=np.float32)
        tokens = [t for t in text.lower().split() if t]
        if not tokens:
            return vec.tolist()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + (digest[5] / 255.0)
            vec[idx] += sign * weight
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: List[list[float]] = []
        for text in texts:
            if not text:
                vectors.append([])
                continue
            if self.use_remote:
                try:
                    result = genai.embed_content(
                        model=self.model,
                        content=text,
                        task_type="RETRIEVAL_DOCUMENT",
                    )
                    vectors.append(result["embedding"])
                    continue
                except Exception:
                    # fall back automatically so sync/search never hard-fails on missing API quota/key
                    pass
            vectors.append(self._fallback_embed(text))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed([text])
        return vectors[0] if vectors else []
