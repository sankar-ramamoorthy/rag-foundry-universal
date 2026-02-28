# ingestion_service/src/core/embedders/ollama.py
import requests
import logging
from typing import List

from shared.embedders.base import BaseEmbedder
from shared.chunks import Chunk

logging.basicConfig(level=logging.DEBUG)


class OllamaEmbedder(BaseEmbedder):
    name = "ollama"
    dimension = 768

    def __init__(self, base_url: str, model: str, batch_size: int = 50):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        logging.debug("OllamaEmbedder self.base_url %s", self.base_url)
        logging.debug("OllamaEmbedder self.model %s", self.model)

    def embed(self, chunks: List[Chunk]) -> List[List[float]]:
        logging.debug(
            "OllamaEmbedder received %d items, types: %s",
            len(chunks),
            [type(c).__name__ for c in chunks[:3]],
        )
        texts = [chunk.content for chunk in chunks]
        try:
            payload = {"model": self.model, "input": texts}
            logging.debug("OllamaEmbedder.embed payload %s", payload)
            logging.debug("OllamaEmbedder starting embedding")
            response = requests.post(f"{self.base_url}/api/embed", json=payload)
            logging.debug("OllamaEmbedder finished embedding")
            logging.debug("OllamaEmbedder response: %s", response)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama embedding failed "
                    f"(status={response.status_code}): {response.text}"
                )
            result = response.json()
            logging.debug("OllamaEmbedder response.json: %s", result)
            return (
                result.get("embeddings", [result["embeddings"]])
                if isinstance(texts, list)
                else [result["embeddings"]]
            )
        except Exception as e:
            raise RuntimeError(f"Ollama embedder error: {e}") from e
