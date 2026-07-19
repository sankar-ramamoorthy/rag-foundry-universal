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
        # F-07: second index by extractor-local "id" so builder passes are
        # O(1) lookups instead of full scans. Internal only — never persisted.
        self.entities_by_id: Dict[str, dict] = {}
        self.files: Dict[str, List[str]] = {}  # relative_path -> [canonical_id]
        self.relationships: List[dict] = []
        # F-03: call-site evidence records from the extractor — never
        # entities, never persisted as nodes. Consumed by _resolve_calls.
        self.call_sites: List[dict] = []
        # F-02: per-file import bindings (local name -> resolved target),
        # built by _resolve_imports. In-memory only; consumed by call
        # resolution (ADR-032 layer 2).
        self.import_bindings: Dict[str, dict] = {}
        # WP-G5: class entity id -> resolved intra-repo base CLASS entity
        # ids, in declaration order. Built by _resolve_inheritance;
        # consumed by self/cls call resolution. In-memory only.
        self.class_bases: Dict[str, List[str]] = {}

    def add_entity(self, relative_path: str, entity: dict):
        """
        Add an artifact to the graph.

        The entity must already contain:
            - canonical_id
        """
        canonical_id = entity["canonical_id"]
        self.entities[canonical_id] = entity
        entity_id = entity.get("id")
        if entity_id is not None:
            self.entities_by_id[entity_id] = entity
        self.files.setdefault(relative_path, []).append(canonical_id)

    def get_entity(self, canonical_id: str) -> dict | None:
        """
        Retrieve an artifact by canonical ID.
        """
        return self.entities.get(canonical_id)

    def get_entity_by_id(self, entity_id: str) -> dict | None:
        """
        Retrieve an artifact by its extractor-local "id".
        """
        return self.entities_by_id.get(entity_id)

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
