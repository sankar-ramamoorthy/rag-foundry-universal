# llm_service/tests/core/test_model_policy.py
"""
WP-M7: runtime-persisted model policy -- file-backed slot overrides.
"""
import json

import pytest

from src.core import model_policy


@pytest.fixture()
def policy_path(tmp_path, monkeypatch):
    path = tmp_path / "model-policy.json"
    monkeypatch.setenv("MODEL_POLICY_PATH", str(path))
    return path


def test_missing_file_loads_empty_defaults(policy_path):
    data = model_policy.load_policy()
    assert data == {"version": 1, "slots": {}}


def test_write_then_load_round_trip(policy_path):
    model_policy.write_slot("fast", "groq/llama-3.1-8b-instant", updated_by="tester")
    data = model_policy.load_policy()

    assert data["version"] == 1
    slot = data["slots"]["fast"]
    assert slot["model"] == "groq/llama-3.1-8b-instant"
    assert slot["updated_by"] == "tester"
    assert "updated_at" in slot


def test_write_creates_parent_directory(tmp_path, monkeypatch):
    nested = tmp_path / "nested" / "dir" / "model-policy.json"
    monkeypatch.setenv("MODEL_POLICY_PATH", str(nested))
    model_policy.write_slot("fast", "groq/llama-3.1-8b-instant")
    assert nested.is_file()


def test_write_is_atomic_replace_no_tmp_left_behind(policy_path):
    model_policy.write_slot("fast", "groq/llama-3.1-8b-instant")
    leftovers = list(policy_path.parent.glob("*.tmp"))
    assert leftovers == []
    assert policy_path.is_file()


SMART_MODEL = "openrouter/meta-llama/llama-3.3-70b-instruct:free"


def test_write_preserves_other_slots(policy_path):
    model_policy.write_slot("fast", "groq/llama-3.1-8b-instant")
    model_policy.write_slot("smart", SMART_MODEL)

    data = model_policy.load_policy()
    assert set(data["slots"]) == {"fast", "smart"}


def test_clear_slot_removes_only_that_slot(policy_path):
    model_policy.write_slot("fast", "groq/llama-3.1-8b-instant")
    model_policy.write_slot("smart", SMART_MODEL)

    model_policy.clear_slot("fast")
    data = model_policy.load_policy()
    assert set(data["slots"]) == {"smart"}


def test_clear_slot_missing_is_a_noop(policy_path):
    model_policy.clear_slot("never-existed")
    data = model_policy.load_policy()
    assert data["slots"] == {}


def test_corrupt_json_raises_model_policy_error(policy_path):
    policy_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(model_policy.ModelPolicyError):
        model_policy.load_policy()


def test_malformed_shape_raises_model_policy_error(policy_path):
    policy_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(model_policy.ModelPolicyError):
        model_policy.load_policy()
