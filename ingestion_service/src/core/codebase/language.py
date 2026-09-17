"""Path-derived artifact language, shared by graph assembly and embedding."""

from pathlib import PurePosixPath


LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".java": "java",
}


def language_for_path(relative_path: str) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(relative_path).suffix)
