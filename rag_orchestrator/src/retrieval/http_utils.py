from typing import Set, List
from .types import RetrievedChunk
import logging

logger = logging.getLogger(__name__)

def extract_canonical_ids_from_chunks(chunks: List[RetrievedChunk]) -> Set[str]:
    """
    Extract canonical_ids from chunk metadata.
    """
    canonical_ids = {
        canonical_id
        for chunk in chunks
        if chunk.metadata and (canonical_id := chunk.metadata.get("canonical_id")) is not None
    }
    logger.debug(f"Extracted {len(canonical_ids)} canonical_ids from {len(chunks)} chunks")
    return canonical_ids
