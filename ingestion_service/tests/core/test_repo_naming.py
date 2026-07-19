# ingestion_service/tests/core/test_repo_naming.py
"""
Issue #30 Part 5: repository names derive from ingestion metadata
(git_url / local_path), not from the repo UUID.
"""
import pytest

from src.core.repo_naming import derive_repo_identity

pytestmark = pytest.mark.unit


def test_https_url_with_git_suffix():
    identity = derive_repo_identity(
        {"git_url": "https://github.com/sankar-ramamoorthy/rag-foundry-universal.git"}
    )
    assert identity["source_type"] == "git"
    assert identity["name"] == "rag-foundry-universal"
    assert identity["display_name"] == "sankar-ramamoorthy/rag-foundry-universal"
    assert identity["git_url"].startswith("https://")
    assert identity["local_path"] is None


def test_https_url_without_git_suffix_and_trailing_slash():
    identity = derive_repo_identity({"git_url": "https://github.com/owner/repo/"})
    assert identity["name"] == "repo"
    assert identity["display_name"] == "owner/repo"


def test_scp_style_ssh_url():
    identity = derive_repo_identity({"git_url": "git@github.com:owner/repo.git"})
    assert identity["source_type"] == "git"
    assert identity["name"] == "repo"
    assert identity["display_name"] == "owner/repo"


def test_ssh_scheme_url():
    identity = derive_repo_identity({"git_url": "ssh://git@gitlab.com/group/project.git"})
    assert identity["name"] == "project"
    assert identity["display_name"] == "group/project"


def test_same_repo_name_different_owners_stay_distinguishable():
    a = derive_repo_identity({"git_url": "https://github.com/alice/tool.git"})
    b = derive_repo_identity({"git_url": "https://github.com/bob/tool.git"})
    assert a["name"] == b["name"] == "tool"
    assert a["display_name"] != b["display_name"]


def test_windows_local_path():
    identity = derive_repo_identity({"local_path": "C:\\Users\\bosto\\repos\\my_test_repo"})
    assert identity["source_type"] == "local"
    assert identity["name"] == "my_test_repo"
    assert identity["display_name"] == "my_test_repo — C:\\Users\\bosto\\repos\\my_test_repo"
    assert identity["git_url"] is None


def test_posix_local_path_with_trailing_slash():
    identity = derive_repo_identity({"local_path": "/data/repos/my_repo/"})
    assert identity["name"] == "my_repo"
    assert identity["local_path"] == "/data/repos/my_repo/"


def test_git_url_wins_over_local_path():
    identity = derive_repo_identity(
        {"git_url": "https://github.com/o/r.git", "local_path": "/tmp/clone"}
    )
    assert identity["source_type"] == "git"
    assert identity["name"] == "r"


def test_unparseable_git_url_falls_back_to_none():
    identity = derive_repo_identity({"git_url": "not a url"})
    assert identity["source_type"] == "git"
    assert identity["name"] is None
    assert identity["display_name"] is None


def test_missing_metadata_yields_all_none():
    for metadata in (None, {}, {"provider": "ollama"}):
        identity = derive_repo_identity(metadata)
        assert identity["source_type"] is None
        assert identity["name"] is None
        assert identity["display_name"] is None


def test_branch_passthrough():
    identity = derive_repo_identity(
        {"git_url": "https://github.com/o/r.git", "branch": "develop"}
    )
    assert identity["branch"] == "develop"
