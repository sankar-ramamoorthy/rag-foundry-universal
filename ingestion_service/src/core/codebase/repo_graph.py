# ingestion_service/src/core/codebase/repo_graph.py
"""
RepoGraph

In-memory representation of a repository graph.

Holds extracted artifacts by canonical ID and file-organized lists of IDs.
Supports explicit relationships (CALLs, DEFINES, etc.).

Relationship format (normalized):

{
    "from_canonical_id": str,
    "to_canonical_id": str,
    "relation_type": str,              # e.g. "CALL", "DEFINES"
    "relationship_metadata": dict      # optional metadata
}
"""

from pathlib import Path
from typing import Dict, List


class RepoGraph:
    """
    Stores artifacts and relationships for a repository.
    """

    def __init__(self, repo_root: Path, ingestion_id: str):
        self.repo_root = repo_root
        self.ingestion_id = ingestion_id
        self.entities: Dict[str, dict] = {}  # canonical_id -> artifact dict
        self.files: Dict[str, List[str]] = {}  # relative_path -> [canonical_id]
        self.relationships: List[dict] = []

    def add_entity(self, relative_path: str, entity: dict):
        """
        Add an artifact to the graph.

        The entity must already contain:
            - canonical_id
        """
        canonical_id = entity["canonical_id"]
        self.entities[canonical_id] = entity
        self.files.setdefault(relative_path, []).append(canonical_id)

    def get_entity(self, canonical_id: str) -> dict | None:
        """
        Retrieve an artifact by canonical ID.
        """
        return self.entities.get(canonical_id)

    def all_entities(self) -> list[dict]:
        """
        Return all artifact dictionaries.
        """
        return list(self.entities.values())

    def add_relationship(self, relationship: dict):
        """
        Add a normalized relationship.

        Required keys:
            - from_canonical_id
            - to_canonical_id
            - relation_type
        Optional:
            - relationship_metadata
        """
        self.relationships.append(relationship)
