from __future__ import annotations

import os
from typing import List

import google.generativeai as genai
import numpy as np


class EmbeddingService:
    def __init__(self, model: str = "models/text-embedding-004"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for embeddings")
        self.model = model
        genai.configure(api_key=api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: List[list[float]] = []
        for text in texts:
            if not text:
                vectors.append([])
                continue
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
            )
            vectors.append(result["embedding"])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed([text])
        return vectors[0] if vectors else []
