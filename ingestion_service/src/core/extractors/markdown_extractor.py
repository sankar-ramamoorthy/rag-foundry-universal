# ingestion_service/src/core/extractors/markdown_extractor.py
# Markdown Section Extraction into Unified Artifact Graph (ADR-043)
"""
MarkdownSectionExtractor

Extracts section artifacts from Markdown files using markdown-it-py.

Emits:
- MARKDOWN_MODULE  : one per file (the file itself)
- MARKDOWN_SECTION : one per heading, nested via parent_id

Canonical ID format:
    README.md                            ← module
    README.md#installation               ← h1 section
    README.md#installation.docker_setup  ← h2 nested under installation

Relationship type: DEFINES (parent DEFINES child section)
Consistent with Python class → method pattern.
"""

import re
import logging
from typing import List, Dict, Optional
from markdown_it import MarkdownIt

logger = logging.getLogger(__name__)


class MarkdownSectionExtractor:
    """
    Extracts MARKDOWN_MODULE and MARKDOWN_SECTION artifacts from a .md file.
    Returns same List[Dict] shape as PythonASTExtractor for RepoGraphBuilder compatibility.
    """

    def __init__(self, relative_path: str):
        self.relative_path = relative_path
        self.module_id = relative_path
        self._slug_counts: Dict[str, int] = {}   # for deduplication

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, source: str) -> List[Dict]:
        """
        Parse markdown source and return list of artifact dicts.

        Args:
            source: Raw markdown text

        Returns:
            List of artifact dicts compatible with RepoGraphBuilder
        """
        self._slug_counts = {}   # reset per extraction
        artifacts: List[Dict] = []

        # Always emit MODULE node first
        artifacts.append({
            "artifact_type": "MARKDOWN_MODULE",
            "id": self.module_id,
            "name": self._stem(self.relative_path),
            "relative_path": self.relative_path,
            "doc_type": "markdown_module",
            "metadata": {},
            "text": source,
        })

        # Parse headings
        sections = self._parse_sections(source)
        artifacts.extend(sections)

        logger.debug(
            f"MS6-IS2: {self.relative_path} → "
            f"1 module + {len(sections)} sections"
        )
        return artifacts

    # ------------------------------------------------------------------
    # Section Parsing
    # ------------------------------------------------------------------

    def _parse_sections(self, source: str) -> List[Dict]:
        """
        Parse markdown into SECTION artifacts using markdown-it-py token stream.
        Maintains a heading stack to resolve parent-child relationships.
        """
        md = MarkdownIt()
        tokens = md.parse(source)
        lines = source.splitlines(keepends=True)

        sections: List[Dict] = []

        # heading_stack: list of (level, canonical_id, slug)
        heading_stack: List[tuple] = []

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.type == "heading_open":
                level = int(token.tag[1])  # h1→1, h2→2 etc
                lineno = token.map[0] + 1 if token.map else None

                # Next token is inline content
                inline_token = tokens[i + 1] if i + 1 < len(tokens) else None
                heading_text = inline_token.content if inline_token else ""

                # Build slug
                slug = self._slugify(heading_text)
                slug = self._deduplicate_slug(slug)

                # Resolve parent from heading stack
                parent_canonical_id, canonical_id = self._resolve_ids(
                    level, slug, heading_stack
                )

                # Update heading stack
                # Pop anything at same or deeper level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, canonical_id, slug))

                # Find section text: from this heading line to next same-or-higher heading
                section_text = self._slice_section_text(
                    lines, lineno, level, tokens, i
                )

                sections.append({
                    "artifact_type": "MARKDOWN_SECTION",
                    "id": canonical_id,
                    "name": heading_text,
                    "parent_id": parent_canonical_id,
                    "relative_path": self.relative_path,
                    "doc_type": "markdown_section",
                    "metadata": {
                        "level": level,
                        "lineno": lineno,
                        "slug": slug,
                    },
                    "text": section_text,
                })

            i += 1

        return sections

    # ------------------------------------------------------------------
    # ID Resolution
    # ------------------------------------------------------------------

    def _resolve_ids(
        self,
        level: int,
        slug: str,
        heading_stack: List[tuple],
    ) -> tuple:
        """
        Returns (parent_canonical_id, canonical_id) for this heading.

        Rules:
            - H1: parent is module, canonical = path#slug
            - H2+: parent is nearest heading with level < current
                   canonical = path#parent_slug.slug
        """
        # Find parent — nearest entry in stack with lower level
        parent_entry = None
        for entry in reversed(heading_stack):
            if entry[0] < level:
                parent_entry = entry
                break

        if parent_entry is None:
            # Top-level heading — parent is the module
            parent_canonical_id = self.module_id
            canonical_id = f"{self.relative_path}#{slug}"
        else:
            parent_canonical_id = parent_entry[1]
            # Build nested slug from parent canonical_id
            # parent canonical_id = "path#a.b", append ".slug"
            parent_slug_part = parent_canonical_id.split("#", 1)[1] \
                if "#" in parent_canonical_id else ""
            canonical_id = f"{self.relative_path}#{parent_slug_part}.{slug}"

        return parent_canonical_id, canonical_id

    # ------------------------------------------------------------------
    # Section Text Slicing
    # ------------------------------------------------------------------

    def _slice_section_text(
        self,
        lines: List[str],
        start_lineno: Optional[int],
        current_level: int,
        tokens: list,
        current_token_index: int,
    ) -> str:
        """
        Extract text from this heading line up to (not including)
        the next heading at same or higher level.
        """
        if start_lineno is None:
            return ""

        # Find the line number where the next same-or-higher heading starts
        end_lineno = len(lines) + 1   # default: end of file

        for j in range(current_token_index + 1, len(tokens)):
            t = tokens[j]
            if t.type == "heading_open":
                next_level = int(t.tag[1])
                if next_level <= current_level:
                    if t.map:
                        end_lineno = t.map[0]   # 0-based line index
                    break

        # start_lineno is 1-based; lines is 0-based
        start_idx = start_lineno - 1
        end_idx = end_lineno  # end_lineno from token.map is already 0-based

        return "".join(lines[start_idx:end_idx]).strip()

    # ------------------------------------------------------------------
    # Slug Helpers
    # ------------------------------------------------------------------

    def _slugify(self, text: str) -> str:
        """
        Convert heading text to canonical slug.
        Rules (ADR-043):
            - lowercase
            - strip leading/trailing whitespace
            - replace spaces and punctuation with underscores
            - letters, digits, underscores only
        """
        slug = text.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "_", slug)
        slug = slug.strip("_")
        return slug or "section"

    def _deduplicate_slug(self, slug: str) -> str:
        """
        Append numeric suffix for duplicate slugs within same file.
        First occurrence: no suffix
        Second: slug_2, Third: slug_3, etc.
        """
        count = self._slug_counts.get(slug, 0) + 1
        self._slug_counts[slug] = count
        if count == 1:
            return slug
        return f"{slug}_{count}"

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _stem(relative_path: str) -> str:
        """Extract filename stem: 'docs/README.md' → 'README'"""
        return relative_path.split("/")[-1].rsplit(".", 1)[0]