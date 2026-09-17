"""Work-boundary checks for owned ingestion threads, without global state."""

from collections.abc import Callable
from contextvars import ContextVar


ownership_check: ContextVar[Callable[[], None] | None] = ContextVar(
    "ingestion_ownership_check", default=None,
)


def check_ownership() -> None:
    check = ownership_check.get()
    if check is not None:
        check()
