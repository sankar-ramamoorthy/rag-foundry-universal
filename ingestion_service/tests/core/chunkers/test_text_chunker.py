#ingestion_service\tests\core\chunkers\test_text_chunker.py
import pytest
from src.core.chunkers.text import TextChunker

def test_simple_chunking():
    text = "a" * 1200
    chunker = TextChunker(chunk_size=500, overlap=0, chunk_strategy="simple")

    chunks = chunker.chunk(text)

    assert len(chunks) == 3
    assert all(len(c.content) <= 500 for c in chunks)
    assert all(c.chunk_id for c in chunks)

def test_sentence_chunking():
    text = "Hello world. This is a test. Another sentence."
    chunker = TextChunker(chunk_strategy="sentence")

    chunks = chunker.chunk(text, chunk_size=20)

    assert len(chunks) >= 2
    assert all(c.content.strip() for c in chunks)

def test_paragraph_chunking():
    text = "CSS General Earl Van Dorn was a cottonclad warship used by the Confederate\
          States of America during the American Civil War. \
            Purchased for Confederate service in New Orleans in early 1862 \
                to serve with the River Defense Fleet, she was converted into a \
                    cottonclad warship by installing an iron-covered framework of  \
                    timbers on her bow that served as a ram, and protecting her  \
                    machinery with timber bulkheads packed with cotton. \
                        A sidewheel steamer, she was 182 feet (55 m) long and \
                            was armed with a single 32-pounder cannon on the bow. \
                                Initially assigned to defend the Mississippi River, \
                                    she arrived at Memphis, Tennessee, in April 1862. \
                                        On May 10, she fought with the River Defense Fleet\
                                              against the Union navy in the Battle of \
                                                Plum Point Bend (pictured),\
                                                      where she rammed and sank USS Mound City. \
                                                        After withdrawing up the Yazoo River to Liverpool Landing, Mississippi,\
                                                              General Earl Van Dorn, along with two other warships, \
                                                                was burnt to prevent her capture by approaching Union \
                                                                    vessels.\n\nHermann Schwarz 	Hermann Schwarz (25 January 1843 – 30 November 1921) was a German mathematician, known for his work in complex analysis. Between 1867 and 1869, he worked at the University of Halle, then at the Swiss Federal Polytechnic in Zurich. From 1875, Schwarz worked at Göttingen University, dealing with the subjects of complex analysis, differential geometry, and the calculus of variations. In 1892, he became a member of the Berlin Academy of Science and a professor at the University of Berlin, where his students included Lipót Fejér, Paul Koebe and Ernst Zermelo. Schwarz's name is attached to many ideas in mathematics. This photograph of Schwarz, taken around 1890, is in the collection of the ETH Library. .\n\nPara three."
    chunker = TextChunker(chunk_strategy="paragraph")

    chunks = chunker.chunk(text, chunk_size=50)

    assert len(chunks) == 3

def test_paragraph_chunking_merges_small_paragraphs():
    """
    Test paragraph strategy in TextChunker.
    
    Current behavior:
    - Paragraphs are merged until the combined length exceeds chunk_size.
    - This test checks that small paragraphs are merged into fewer chunks.
    """
    text = "Para one.\n\nPara two.\n\nPara three."
    chunker = TextChunker(chunk_strategy="paragraph")
    chunks = chunker.chunk(text, chunk_size=50)  # buffer allows merging all 3

    # All three paragraphs are merged because total length < 50
    assert len(chunks) == 1
    assert "Para one." in chunks[0].content
    assert "Para two." in chunks[0].content
    assert "Para three." in chunks[0].content


def test_unknown_strategy_raises():
    chunker = TextChunker(chunk_strategy="unknown")

    with pytest.raises(ValueError):
        chunker.chunk("text")
