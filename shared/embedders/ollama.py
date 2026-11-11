import requests
import logging
from typing import List
from shared.embedders.base import BaseEmbedder
from shared.embedders.input_contract import EMBEDDING_INPUT_CONTRACT
from shared.chunks import Chunk

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ollama's error text when an input exceeds the model context and the request
# set "truncate": false.
_CONTEXT_OVERFLOW = "exceeds the context length"


class OllamaEmbedder(BaseEmbedder):
    """Embed chunk text exactly as given (CI-06, #337).

    The client never shortens input, and requests set ``truncate: false`` so
    Ollama rejects an over-context input instead of silently encoding a
    prefix. Such an input is isolated and, as a last resort, embedded with
    server-side truncation; that chunk is marked
    ``metadata["embedding_input"]["truncated"] = True`` and logged, so the
    loss is recorded on the persisted vector rather than hidden. Chunkers
    size passages to ``shared.embedders.input_contract`` so this should not
    happen for ingested passages.
    """

    name = "ollama"
    input_contract = EMBEDDING_INPUT_CONTRACT

    def __init__(self, base_url: str, model: str, batch_size: int = 50,
                  dimension: int | None = None,):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.dimension = dimension or 1024
        self.truncated_inputs = 0

        logger.debug(
            "OllamaEmbedder base_url=%s model=%s dimension=%d",
            self.base_url, self.model, self.dimension
        )

    def _post(self, texts: List[str], truncate: bool) -> requests.Response:
        # Finite connect/read deadlines; provider hangs must surface as
        # ingestion failure. This is per HTTP batch, not a job deadline.
        return requests.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": texts, "truncate": truncate},
            timeout=(10, 120),
        )

    @staticmethod
    def _vectors(response: requests.Response, expected: int) -> List[List[float]]:
        if response.status_code != 200:
            raise RuntimeError(
                f"Ollama embedding failed "
                f"(status={response.status_code}): {response.text}"
            )
        vectors = response.json()["embeddings"]
        if len(vectors) != expected:
            raise RuntimeError(
                f"Ollama returned {len(vectors)} embeddings for {expected} inputs"
            )
        return vectors

    @staticmethod
    def _overflowed(response: requests.Response) -> bool:
        return response.status_code != 200 and _CONTEXT_OVERFLOW in response.text

    def _embed_batch(self, chunks: List[Chunk]) -> List[List[float]]:
        texts = [chunk.content for chunk in chunks]
        response = self._post(texts, truncate=False)
        if not self._overflowed(response):
            return self._vectors(response, len(texts))
        if len(chunks) > 1:
            # Isolate which input(s) overflowed; the rest stay exact.
            vectors: List[List[float]] = []
            for chunk in chunks:
                vectors.extend(self._embed_batch([chunk]))
            return vectors

        chunk = chunks[0]
        self.truncated_inputs += 1
        chunk.metadata.setdefault("embedding_input", {})["truncated"] = True
        logger.warning(
            "OllamaEmbedder: input of %d chars exceeds the %s context; embedded "
            "a server-truncated prefix (canonical_id=%s)",
            len(texts[0]), self.model, chunk.metadata.get("canonical_id"),
        )
        return self._vectors(self._post(texts, truncate=True), 1)

    def embed(self, chunks: List[Chunk]) -> List[List[float]]:
        logger.debug("OllamaEmbedder received %d items", len(chunks))
        if not chunks:
            return []

        for chunk in chunks:
            if chunk.metadata is None:
                chunk.metadata = {}
            chunk.metadata["embedding_input"] = {
                "contract": EMBEDDING_INPUT_CONTRACT,
                "truncated": False,
            }

        embeddings: List[List[float]] = []
        try:
            for start in range(0, len(chunks), self.batch_size):
                embeddings.extend(
                    self._embed_batch(chunks[start:start + self.batch_size])
                )
        except Exception as e:
            raise RuntimeError(f"Ollama embedder error: {e}") from e

        if len(embeddings) != len(chunks):
            raise RuntimeError(
                f"Ollama returned {len(embeddings)} embeddings "
                f"for {len(chunks)} inputs"
            )
        return embeddings
