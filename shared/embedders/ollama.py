import requests
import logging
from typing import List
from shared.embedders.base import BaseEmbedder
from shared.chunks import Chunk

logging.basicConfig(level=logging.DEBUG)

MAX_EMBEDDING_WORDS = 400
MAX_EMBEDDING_CHARS = 800


def _truncate(text: str, max_words: int = MAX_EMBEDDING_WORDS) -> str:
    if len(text) > MAX_EMBEDDING_CHARS:
        logging.debug(
            "OllamaEmbedder: truncated chunk by chars from %d to %d",
            len(text), MAX_EMBEDDING_CHARS,
        )
        text = text[:MAX_EMBEDDING_CHARS]

    words = text.split()
    if len(words) <= max_words:
        return text

    logging.debug(
        "OllamaEmbedder: truncated chunk from %d words to %d words",
        len(words), max_words,
    )
    return " ".join(words[:max_words])


class OllamaEmbedder(BaseEmbedder):
    name = "ollama"

    def __init__(self, base_url: str, model: str, batch_size: int = 50, dimension: int = 1024):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.dimension = dimension

        logging.debug(
            "OllamaEmbedder base_url=%s model=%s dimension=%d",
            self.base_url, self.model, self.dimension
        )

    def embed(self, chunks: List[Chunk]) -> List[List[float]]:
        logging.debug(
            "OllamaEmbedder received %d items",
            len(chunks),
        )

        texts = [_truncate(chunk.content) for chunk in chunks]

        try:
            payload = {"model": self.model, "input": texts}

            response = requests.post(f"{self.base_url}/api/embed", json=payload)

            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama embedding failed "
                    f"(status={response.status_code}): {response.text}"
                )

            result = response.json()

            return (
                result.get("embeddings", [result["embeddings"]])
                if isinstance(texts, list)
                else [result["embeddings"]]
            )

        except Exception as e:
            raise RuntimeError(f"Ollama embedder error: {e}") from e