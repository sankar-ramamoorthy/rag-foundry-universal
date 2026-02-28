#ingestion_service\tests\core\chunkers\test_chunk_model.py
from src.core.chunks import Chunk

def test_chunk_defaults():
    chunk = Chunk(chunk_id="id1", content="hello")
    assert chunk.chunk_id == "id1"
    assert chunk.content == "hello"
    assert chunk.metadata == {}
    assert chunk.ocr_text is None
