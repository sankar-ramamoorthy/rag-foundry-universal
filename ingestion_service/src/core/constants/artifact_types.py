"""
ingestion_service/src/core/constants/artifact_types.py

Canonical artifact types used across the Codebase-KG-RAG system.

All artifact_type values should be used when creating DocumentNodes
or building the Codebase Knowledge Graph (KG).

No logic — constants only.
"""

# Documents / ADRs
DOCUMENT = "DOCUMENT"
ADR = "ADR"

# Python code entities
MODULE = "MODULE"
CLASS = "CLASS"
FUNCTION = "FUNCTION"
METHOD = "METHOD"

# Testing
TEST = "TEST"

# Repositories
REPO = "REPO"  # optional node type to represent repositories themselves

# Future / placeholder types
TODO = "TODO"          # reserved for future use if needed
DEPRECATED = "DEPRECATED"  # can be flagged during ingestion
