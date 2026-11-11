import requests
import logging
from typing import List, Optional
from shared.embedders.base import BaseEmbedder, EmbeddingInputTooLong
from shared.embedders.input_contract import EMBEDDING_INPUT_CONTRACT
from shared.chunks import Chunk

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Ollama's error text when an input exceeds the model context and the request
# set "truncate": false.
_CONTEXT_OVERFLOW = "exceeds the context length"


class OllamaEmbedder(BaseEmbedder):
    """Embed chunk text exactly as given (CI-06, #337).

    Requests always set ``truncate: false``, so Ollama rejects an over-context
    input instead of silently encoding a prefix, and the client never shortens
    input. A rejected batch is bisected to find the offending inputs while the
    rest are embedded normally.

    - Stored passages (default): offenders raise
      :class:`EmbeddingInputTooLong`; the ingestion pipeline splits them.
    - Queries (``truncate_overflow=True``): offenders are re-sent with
      server-side truncation, logged, and marked
      ``metadata["embedding_input"]["truncated"] = True``.
    """

    name = "ollama"
    input_contract = EMBEDDING_INPUT_CONTRACT

    def __init__(self, base_url: str, model: str, batch_size: int = 50,
                  dimension: int | None = None,):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.batch_size = batch_size
        self.dimension = dimension or 1024
        self.truncated_queries = 0

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

    def _strict(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Embed with truncation disabled; ``None`` marks a rejected input.

        Bisection costs O(k log n) extra requests for k offenders in a batch
        of n, instead of one request per input.
        """
        response = self._post(texts, truncate=False)
        if not self._overflowed(response):
            return list(self._vectors(response, len(texts)))
        if len(texts) == 1:
            return [None]
        middle = len(texts) // 2
        return self._strict(texts[:middle]) + self._strict(texts[middle:])

    def embed(
        self, chunks: List[Chunk], *, truncate_overflow: bool = False
    ) -> List[List[float]]:
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

        vectors: List[Optional[List[float]]] = []
        try:
            for start in range(0, len(chunks), self.batch_size):
                batch = chunks[start:start + self.batch_size]
                vectors.extend(self._strict([c.content for c in batch]))
            rejected = [i for i, v in enumerate(vectors) if v is None]
            if rejected and truncate_overflow:
                for i in rejected:
                    vectors[i] = self._truncated_query(chunks[i])
                rejected = []
        except Exception as e:
            raise RuntimeError(f"Ollama embedder error: {e}") from e

        if rejected:
            raise EmbeddingInputTooLong(rejected, vectors)
        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"Ollama returned {len(vectors)} embeddings "
                f"for {len(chunks)} inputs"
            )
        return [v for v in vectors if v is not None]

    def _truncated_query(self, chunk: Chunk) -> List[float]:
        self.truncated_queries += 1
        chunk.metadata["embedding_input"]["truncated"] = True
        logger.warning(
            "OllamaEmbedder: query of %d chars exceeds the %s context; "
            "embedded a server-truncated prefix",
            len(chunk.content), self.model,
        )
        return self._vectors(self._post([chunk.content], truncate=True), 1)[0]
