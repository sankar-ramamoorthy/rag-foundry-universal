"""Embedding-input contract shared by chunking and embedding (CI-06, #337).

Invariant: a stored passage is the exact text the embedding model encodes.
Chunkers size passages to these budgets; embedders must not shorten them.
See DOCS/adr/ADR-056-embedding-input-contract.md for the decision and the
CI-06 investigation for the measurements behind the numbers.
"""

# Identifies this contract in the incremental-reuse gate. Bump it whenever a
# budget below or the embedder's input handling changes, so vectors built
# under a different contract are re-embedded instead of reused.
EMBEDDING_INPUT_CONTRACT = "exact-input-v2"

# Character cap per passage. mxbai-embed-large has a 512-token context; at
# 800 characters code passages measured a median of ~180 tokens.
EMBEDDING_INPUT_MAX_CHARS = 800

# Cap on shared.chunkers.text.estimate_tokens() per passage. The estimate
# overstates real WordPiece counts, so 480 leaves headroom under 512 for
# punctuation-dense tables and CJK text, which the character cap alone
# does not bound.
EMBEDDING_INPUT_MAX_EST_TOKENS = 480

# Whole trailing lines repeated between consecutive windows of one artifact.
EMBEDDING_INPUT_OVERLAP_CHARS = 100
