"""Batch-local validation shared by embedding and HTTP persistence (#160)."""


def validate_batch_identity(
    count: int, document_ids: list[str], chunk_indices: list[int] | None
) -> None:
    if count != len(document_ids):
        raise ValueError(
            f"Batch mismatch: {count} chunks, {len(document_ids)} document_ids"
        )
    if chunk_indices is None:
        return
    if count != len(chunk_indices):
        raise ValueError(
            f"Batch mismatch: {count} chunks, {len(chunk_indices)} indices"
        )
    seen: set[tuple[str, int]] = set()
    for document_id, index in zip(document_ids, chunk_indices):
        if type(index) is not int or index < 0:
            raise ValueError("chunk_indices must contain nonnegative integers")
        key = (document_id, index)
        if key in seen:
            raise ValueError("Duplicate document_id/chunk_index in batch")
        seen.add(key)
