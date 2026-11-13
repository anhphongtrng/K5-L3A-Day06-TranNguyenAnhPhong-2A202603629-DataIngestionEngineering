
"""Local BGE-M3 embedding adapter."""

from typing import Protocol
from sentence_transformers import SentenceTransformer


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(
        self, texts: list[str]
    ) -> list[list[float]]:
        ...

    def embed_query(
        self, question: str
    ) -> list[float]:
        ...


class MyEmbedder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

        dimension = self.model.get_sentence_embedding_dimension()
        if dimension is None:
            raise ValueError("Unknown embedding dimensions")

        self.dimensions = int(dimension)

    def embed_documents(
        self, texts: list[str]
    ) -> list[list[float]]:
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            batch_size=16,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        return vectors.tolist()

    def embed_query(
        self, question: str
    ) -> list[float]:
        vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )
        return vector.tolist()
