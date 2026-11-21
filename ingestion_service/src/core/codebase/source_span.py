# ingestion_service/src/core/codebase/source_span.py
"""
Verified source line spans (issue #412, specs/014-persisted-source-spans).

Contract: a line range is stored only when it provably covers the artifact's
text in the file, using the same line convention as the source read API (LF
only, one-based, inclusive, terminal LF is not an extra line). If it cannot be
proved, no range is stored. Extractor spans are only a hint: they do not always
match the stored text (a decorated Python definition's text starts at its first
decorator while its span starts at `def`), so every candidate is checked
against the text before it is accepted.

The range names whole lines. The artifact text starts after the first line's
indentation and may be followed on its last line by trailing source (such as a
comment); both are accounted for in the check and nothing else may differ.
"""

from bisect import bisect_left
from typing import Optional, Sequence, Tuple

Range = Tuple[int, int]


def split_lines(file_text: str) -> list[str]:
    """Lines under the source read API's convention: split on LF only, keeping
    each terminator, with no phantom line after a terminal LF."""
    if not file_text:
        return []
    lines = file_text.split("\n")
    out = [line + "\n" for line in lines[:-1]]
    if lines[-1]:
        out.append(lines[-1])
    return out


def verified_range(
    file_lines: Sequence[str], end_line: Optional[int], text: str
) -> Optional[Range]:
    """The (start, end) line range whose source holds `text`, or None.

    `end_line` is the extractor's last line for the artifact. The start is
    derived from the text's own line count, then the whole candidate is
    compared to the text; any mismatch returns None.
    """
    if not text or end_line is None or not 1 <= end_line <= len(file_lines):
        return None
    count = text.count("\n") + (0 if text.endswith("\n") else 1)
    start = end_line - count + 1
    if start < 1:
        return None
    region = file_lines[start - 1 : end_line]
    first = region[0]
    joined = first.lstrip(" \t") + "".join(region[1:])
    if not joined.startswith(text):
        return None
    rest = joined[len(text) :]
    # Only the remainder of the last line may follow the text.
    if rest.find("\n") not in (-1, len(rest) - 1):
        return None
    return start, end_line


def module_range(
    file_lines: Sequence[str], file_text: str, text: str
) -> Optional[Range]:
    """A module node holds the whole file; its range is every line."""
    if not file_lines or text != file_text:
        return None
    return 1, len(file_lines)


def piece_ranges(
    start_line: int, content: str, pieces: Sequence[str]
) -> list[Optional[Range]]:
    """Ranges for consecutive exact pieces of a passage that starts at
    `start_line`. Each is the lines containing that piece. All entries are None
    unless the pieces concatenate back to `content` exactly."""
    if "".join(pieces) != content or any(not p for p in pieces):
        return [None] * len(pieces)
    out: list[Optional[Range]] = []
    offset = 0
    for piece in pieces:
        first = content.count("\n", 0, offset)
        last = content.count("\n", 0, offset + len(piece) - 1)
        out.append((start_line + first, start_line + last))
        offset += len(piece)
    return out


# Reasons a passage window carries no range (issue #416, spec 015 section 3).
REASON_ARTIFACT_UNVERIFIED = "artifact range not verified"
REASON_NO_OFFSET = "window offset not reported"
REASON_MISMATCH = "passage does not match artifact text at reported offset"


class NewlineIndex:
    """Positions of every LF in a text, so the number of lines before any
    character position is a binary search instead of a rescan per window."""

    def __init__(self, text: str):
        self._positions = [i for i, ch in enumerate(text) if ch == "\n"]

    def lines_before(self, position: int) -> int:
        """How many LFs lie strictly before ``position``."""
        return bisect_left(self._positions, position)


def window_range(
    artifact_text: str,
    artifact_start: int,
    offset: int,
    window: str,
    index: Optional[NewlineIndex] = None,
) -> Optional[Range]:
    """Source lines holding one passage window of an artifact, or None.

    ``offset`` is where the chunker cut the window in ``artifact_text``. The
    window is located by that position, never by searching for its content, so
    repeated text and overlapping windows are not ambiguous. The position is
    verified (the slice must equal the window) before it is mapped to lines
    under the source read API's LF-only convention, starting at the artifact's
    own first line. The range names the lines containing the window.
    """
    if (
        type(artifact_start) is not int
        or artifact_start < 1
        or type(offset) is not int
        or offset < 0
        or not window
        or offset + len(window) > len(artifact_text)
        or artifact_text[offset : offset + len(window)] != window
    ):
        return None
    index = index or NewlineIndex(artifact_text)
    first = index.lines_before(offset)
    last = index.lines_before(offset + len(window) - 1)
    return artifact_start + first, artifact_start + last
