# ingestion_service/src/core/codebase/snapshot_diff.py
"""
Snapshot diff classifier (issue #196).

A small, focused module — not a framework — for classifying a repo's
current file-level content hashes against the prior generation's, so
incremental ingestion can decide which files are eligible to skip
re-embedding (FR-006). Pure function over data the caller already has;
no I/O of its own.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SnapshotDiff:
    unchanged: frozenset[str] = field(default_factory=frozenset)
    changed: frozenset[str] = field(default_factory=frozenset)
    new: frozenset[str] = field(default_factory=frozenset)
    deleted: frozenset[str] = field(default_factory=frozenset)


def classify(
    current_hashes: dict[str, str],
    prior_hashes: dict[str, str],
) -> SnapshotDiff:
    """
    Classify each file-level canonical_id into unchanged/changed/new/deleted.

    current_hashes: {canonical_id: content_hash} for the current checkout.
    prior_hashes: {canonical_id: content_hash} for the prior generation.

    A canonical_id in both maps with matching hashes is "unchanged"
    (byte-for-byte only — no semantic hashing, so a whitespace-only edit
    still classifies as "changed"). A canonical_id in both maps with a
    mismatched hash is "changed". A canonical_id only in current_hashes
    is "new". A canonical_id only in prior_hashes is "deleted".
    """
    current_ids = set(current_hashes)
    prior_ids = set(prior_hashes)

    common = current_ids & prior_ids
    unchanged = {
        cid for cid in common if current_hashes[cid] == prior_hashes[cid]
    }
    changed = common - unchanged
    new = current_ids - prior_ids
    deleted = prior_ids - current_ids

    return SnapshotDiff(
        unchanged=frozenset(unchanged),
        changed=frozenset(changed),
        new=frozenset(new),
        deleted=frozenset(deleted),
    )
