# shared/chunkers/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, List

from shared.chunks import Chunk


class BaseChunker(ABC):
    """Abstract interface for chunking any modality."""

    name: str = "base"  # Default name for logging
    chunk_strategy: str = "unknown"  # ✅ ADD THIS

    @abstractmethod
    def chunk(self, content: Any, **params) -> List[Chunk]:
        """
        Chunk content into smaller pieces.

        :param content: text/audio/video/image
        :param params: strategy-specific parameters (chunk_size, overlap, etc.)
        :return: list of Chunk objects
        """
        pass
