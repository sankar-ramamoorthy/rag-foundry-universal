"""#161 ownership unit contracts; PostgreSQL semantics tested separately."""

from unittest.mock import MagicMock

import pytest

from src.core.ingestion_ownership import (
    AdvisoryGuard, OWNER_KEY, OWNER_VERSION, OwnershipLost, lock_key, owned_metadata,
)


pytestmark = pytest.mark.unit


def test_stable_namespaced_signed_lock_keys():
    assert lock_key("attempt", "a") == lock_key("attempt", "a")
    assert lock_key("attempt", "a") != lock_key("repo", "a")
    assert -(2**63) <= lock_key("attempt", "a") < 2**63


def test_user_cannot_override_ownership_marker():
    original = {OWNER_KEY: "forged", "name": "a"}
    assert owned_metadata(original) == {OWNER_KEY: OWNER_VERSION, "name": "a"}
    assert original[OWNER_KEY] == "forged"


def test_guard_detaches_connection_and_closes_on_exception():
    engine = MagicMock()
    connection = engine.raw_connection.return_value
    with pytest.raises(ValueError):
        with AdvisoryGuard(engine):
            connection.detach.assert_called_once()
            assert connection.driver_connection.autocommit is True
            raise ValueError("work failed")
    connection.close.assert_called_once()


def test_lost_connection_is_not_replaced():
    engine = MagicMock()
    with AdvisoryGuard(engine) as guard:
        engine.raw_connection.return_value.cursor.side_effect = OSError("disconnected")
        with pytest.raises(OwnershipLost):
            guard.check()
        with pytest.raises(OwnershipLost):
            guard.try_lock("attempt", "a")
        engine.raw_connection.assert_called_once()
    with pytest.raises(OwnershipLost):
        guard.check()
