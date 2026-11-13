"""Choose a real embedding provider (API or local) and implement this contract."""
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
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dimensions = self.model.get_sentence_embedding_dimension()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        vectors = self.model.encode(
            texts,
            batch_size=16,
            normalize_embeddings=True,
        )
        return vectors.tolist()

    def embed_query(self, question: str) -> list[float]:
        vector = self.model.encode(
            question,
            normalize_embeddings=True,
        )
        return vector.tolist()
