"""Real local sentence-transformer embeddings; no mock fallback is permitted."""
from __future__ import annotations

import math
from typing import Protocol

from sentence_transformers import SentenceTransformer


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """CPU-compatible Sentence Transformers adapter using cosine-normalized vectors."""

    def __init__(self, model_name: str, device: str = "cpu", batch_size: int = 32) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be empty")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_name, device=device)
        get_dimensions = getattr(
            self._model,
            "get_embedding_dimension",
            self._model.get_sentence_embedding_dimension,
        )
        dimensions = get_dimensions()
        if not dimensions:
            raise RuntimeError(f"Model {model_name!r} did not report embedding dimensions")
        self.dimensions = int(dimensions)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Document texts must be non-empty strings")
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        result = vectors.tolist()
        self._validate(result, len(texts))
        return result

    def embed_query(self, question: str) -> list[float]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        return self.embed_documents([question])[0]

    def _validate(self, vectors: list[list[float]], expected_count: int) -> None:
        if len(vectors) != expected_count:
            raise RuntimeError("Embedding model returned an unexpected vector count")
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise RuntimeError(
                    f"Expected {self.dimensions} dimensions, received {len(vector)}"
                )
            if not all(math.isfinite(value) for value in vector):
                raise RuntimeError("Embedding model returned a non-finite value")
