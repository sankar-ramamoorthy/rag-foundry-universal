# ingestion_service/src/core/retrieval/retrieval_plan.py
"""
RetrievalPlan domain model.

A RetrievalPlan represents *intent*, not execution.

It describes:
- which documents seed retrieval
- which additional documents are eligible via relationships
- why those documents were included
- the constraints under which expansion occurred

This object:
- has NO database access
- has NO traversal or execution logic
- is safe to construct, inspect, serialize, and test in isolation
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set


@dataclass
class ExpansionMetadata:
    """
    Metadata describing why a document was included during expansion.

    Attributes:
        source_document_id:
            The document from which this expansion originated.
        relation_type:
            The relationship type that justified inclusion.
    """
    source_document_id: str
    relation_type: str


@dataclass
class RetrievalConstraints:
    """
    Constraints governing how retrieval expansion was planned.

    Attributes:
        max_depth:
            Maximum relationship depth allowed during planning.
            (MS4 default: 1)
        allow_bidirectional:
            Whether incoming relationships were considered.
            (MS4 default: False)
    """
    max_depth: int = 1
    allow_bidirectional: bool = False


@dataclass
class RetrievalPlan:
    """
    Immutable representation of retrieval intent.

    This object answers:
    - What documents are seeds?
    - What documents are additionally eligible?
    - Why was each document included?
    - Under what constraints was the plan formed?

    This object DOES NOT:
    - execute retrieval
    - traverse graphs
    - rank or score results
    """

    # Initial documents requested by the caller
    seed_document_ids: Set[str]

    # Documents added via relationship-based expansion
    expanded_document_ids: Set[str] = field(default_factory=set)

    # Explanation of why documents were expanded
    # Keyed by expanded document_id
    expansion_metadata: Dict[str, ExpansionMetadata] = field(default_factory=dict)

    # Planning constraints
    constraints: RetrievalConstraints = field(default_factory=RetrievalConstraints)

    def to_dict(self) -> dict:
        """
        Serialize the RetrievalPlan into a JSON-safe dictionary.

        Intended for:
        - logging
        - debugging
        - API responses
        - snapshot testing
        """
        return {
            "seed_document_ids": sorted(self.seed_document_ids),
            "expanded_document_ids": sorted(self.expanded_document_ids),
            "expansion_metadata": {
                doc_id: {
                    "source_document_id": meta.source_document_id,
                    "relation_type": meta.relation_type,
                }
                for doc_id, meta in self.expansion_metadata.items()
            },
            "constraints": asdict(self.constraints),
        }
