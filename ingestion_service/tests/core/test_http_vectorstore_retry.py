# #287: bounded retry for transient vector-store failures only.
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.core.http_vectorstore import HttpVectorStore

pytestmark = pytest.mark.unit

TARGET = "src.core.http_vectorstore.requests.post"


def _ok():
    resp = MagicMock()
    resp.json.return_value = {"ok": True}
    resp.raise_for_status.return_value = None
    return resp


def _store():
    return HttpVectorStore("http://vs:8002")


@patch("src.core.http_vectorstore.time.sleep")
@patch("src.core.http_vectorstore.check_ownership")
def test_retries_read_timeout_then_succeeds(_own, sleep):
    with patch(TARGET, side_effect=[requests.ReadTimeout(), _ok()]) as post:
        assert _store().add_vectors([{"a": 1}]) == {"ok": True}
    assert post.call_count == 2
    sleep.assert_called_once()


@patch("src.core.http_vectorstore.time.sleep")
@patch("src.core.http_vectorstore.check_ownership")
def test_gives_up_after_bounded_attempts(_own, _sleep):
    with patch(TARGET, side_effect=requests.ReadTimeout()) as post:
        with pytest.raises(requests.ReadTimeout):
            _store().add_vectors([{"a": 1}])
    assert post.call_count == HttpVectorStore.MAX_ATTEMPTS


@patch("src.core.http_vectorstore.time.sleep")
@patch("src.core.http_vectorstore.check_ownership")
def test_does_not_retry_client_errors(_own, _sleep):
    bad = MagicMock()
    bad.status_code = 422
    bad.raise_for_status.side_effect = requests.HTTPError(response=bad)
    with patch(TARGET, return_value=bad) as post:
        with pytest.raises(requests.HTTPError):
            _store().add_vectors([{"a": 1}])
    assert post.call_count == 1
