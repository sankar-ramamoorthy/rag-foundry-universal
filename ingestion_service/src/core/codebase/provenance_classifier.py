# ingestion_service/src/core/codebase/provenance_classifier.py
"""
Deterministic role/subject/derivation/validity classification (issue
#199, Stage B1; contract: ADR-053, `specs/008-source-authority-provenance`).

Pure function over already-known node-dict fields (`relative_path`,
`doc_type`, `text`) -- no I/O, no LLM call (Constitution Principle I).
Called once per node inside `CodebaseGraphPersistence.persist_graph`
(the single node-upsert chokepoint every extractor/language and the
document-ingestion path already funnel through), so this applies
uniformly without touching each extractor individually.

Origin is deliberately NOT duplicated here: `DocumentNode.repo_id`,
`canonical_id`, `relative_path`, `source`, `ingestion_id`, `doc_type`,
`content_hash` already are that facet (ADR-053) -- callers read those
columns directly, not a copy inside this JSON blob.
"""

import re
from typing import Optional

# Bumped whenever a rule below changes in a way that could flip a prior
# classification -- incremental ingestion must recompute (not skip)
# provenance for an unchanged-bytes node when this changes (ADR-053,
# spec 008 FR-005). v2 (issue #199, Stage B3 finding): widened
# _FIXTURE_PATH_RE to also catch shared/smoke_repo/ -- a real,
# self-documented live-smoke-test fixture the v1 rule missed entirely,
# found by the B3 shadow-diagnostics pass, never applied automatically
# -- see DOCS/test_results/2026-09-19-stage-b3-provenance-shadow-diagnostics.md.
CLASSIFIER_VERSION = "role-subject-v2"
SCHEMA_VERSION = "provenance-v1"

_TEST_PATH_RE = re.compile(r"(^|/)(tests?)(/|$)|_test\.py$|^test_.*\.py$")
# smoke_repo/smoke_tests(?) added in v2 for the observed shared/smoke_repo/
# gap; deliberately not broadened further (e.g. demo/sample/mock) without
# an observed case to justify it (Stage B3's "measured improvement" bar).
_FIXTURE_PATH_RE = re.compile(
    r"(^|/)(fixtures?|examples?|smoke_repos?|smoke_tests?)(/|$)"
)
_HISTORICAL_PATH_RE = re.compile(r"^docs-archive/")
_DESIGN_PATH_RE = re.compile(r"^DOCS/adr/")
_DOCUMENTATION_PATH_RE = re.compile(r"^DOCS/")
_MANIFEST_BASENAME_RE = re.compile(
    r"(^|/)(pyproject\.toml|package\.json|Cargo\.toml|pom\.xml|"
    r"requirements.*\.txt|docker-compose.*\.ya?ml|Dockerfile)$"
)
_FRONTMATTER_STATUS_RE = re.compile(
    r"\A---\s*\n(.*?)\n---", re.DOTALL
)
_STATUS_FIELD_RE = re.compile(r"^status:\s*(\S+)\s*$", re.MULTILINE)

_SOURCE_DOC_TYPE_SUFFIXES = (" source",)


def _classify_role(relative_path: str, doc_type: str) -> tuple[str, str]:
    """Returns (role, basis) -- basis is a short human-readable rule name,
    not free text, so it stays auditable across classifier versions."""
    # Checked before the generic tests/ rule: a path under tests/fixtures/
    # is test infrastructure, but its *content* is exactly the "embedded
    # example describing something else" case Subject exists to catch --
    # the more specific signal wins.
    if _FIXTURE_PATH_RE.search(relative_path):
        return "example_fixture", "path_convention:fixtures_or_examples_dir"
    if _TEST_PATH_RE.search(relative_path):
        return "test", "path_convention:tests_dir_or_suffix"
    if _HISTORICAL_PATH_RE.search(relative_path):
        return "historical", "path_convention:docs_archive"
    if _DESIGN_PATH_RE.search(relative_path):
        return "design", "path_convention:docs_adr"
    if _MANIFEST_BASENAME_RE.search(relative_path):
        return "configuration", "path_convention:manifest_basename"
    if _DOCUMENTATION_PATH_RE.search(relative_path):
        return "documentation", "path_convention:docs_dir"
    if doc_type.endswith(_SOURCE_DOC_TYPE_SUFFIXES):
        return "implementation", "doc_type:source_suffix"
    return "unknown_mixed", "no_matching_rule"


def _classify_subject(relative_path: str) -> tuple[str, Optional[str]]:
    if _FIXTURE_PATH_RE.search(relative_path):
        return "embedded_subject", "path_convention:fixtures_or_examples_dir"
    return "selected_repository", None


def _classify_derivation() -> dict:
    """Every current producer persists deterministic source/structural
    text, never an LLM-generated summary (Constitution Principle I) --
    a `generated_summary` derivation has no producer yet, so this always
    returns `source` until one exists. Not hardcoded as a constant so a
    future generated-summary producer has an obvious place to branch."""
    return {"status": "source"}


def _classify_validity(text: str) -> dict:
    """Reads only a declared `status:` frontmatter field, when present --
    never infers or verifies whether that declaration is still true
    (ADR-053: "distinguish declared status from verified implementation
    truth")."""
    frontmatter_match = _FRONTMATTER_STATUS_RE.match(text or "")
    if frontmatter_match is None:
        return {"declared_status": "unknown"}
    status_match = _STATUS_FIELD_RE.search(frontmatter_match.group(1))
    if status_match is None:
        return {"declared_status": "unknown"}
    return {"declared_status": status_match.group(1)}


def classify_node(
    relative_path: str,
    doc_type: str,
    text: str,
) -> dict:
    """The full ADR-053 provenance envelope for one node, minus Origin
    (already covered by existing DocumentNode columns -- see module
    docstring)."""
    role, role_basis = _classify_role(relative_path, doc_type)
    subject, subject_basis = _classify_subject(relative_path)
    return {
        "role": {"value": role, "basis": role_basis},
        "subject": {"value": subject, "basis": subject_basis},
        "derivation": _classify_derivation(),
        "validity": _classify_validity(text),
        "classification": {
            "schema_version": SCHEMA_VERSION,
            "classifier_version": CLASSIFIER_VERSION,
            "scope": "artifact",
        },
    }
