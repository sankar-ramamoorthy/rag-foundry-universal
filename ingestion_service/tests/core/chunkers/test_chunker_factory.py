#ingestion_service\tests\core\chunkers\test_chunker_factory.py

import pytest
from src.core.chunkers.selector import ChunkerFactory

# Use the path ChunkerFactory returns
from shared.chunkers.text import TextChunker

def test_get_known_chunker():
    chunker = ChunkerFactory.get_chunker("sentence")
    assert isinstance(chunker, TextChunker)

def test_get_unknown_chunker():
    with pytest.raises(ValueError):
        ChunkerFactory.get_chunker("does-not-exist")

def test_choose_strategy_short_text():
    chunker, params = ChunkerFactory.choose_strategy("short text")
    assert chunker.chunk_strategy == "sentence"

def test_choose_strategy_medium_text():
    text = "a" * 3000
    chunker, params = ChunkerFactory.choose_strategy(text)
    assert chunker.chunk_strategy == "paragraph"

def test_choose_strategy_long_text():
    text = "a" * 20000
    chunker, params = ChunkerFactory.choose_strategy(text)
    assert chunker.chunk_strategy == "simple"
