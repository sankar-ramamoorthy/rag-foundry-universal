"""#161: database-wide single-job admission and explicit attempt ownership.

Session advisory locks live on a dedicated, non-pooled connection. They span
HTTP calls without an open SQL transaction. They are NOT cross-service fencing:
an already dispatched vector write may finish after ownership is lost (R3).
"""

from hashlib import blake2b
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.core.models import IngestionRequest
from src.core.status_manager import StatusManager


OWNER_KEY = "_ingestion_owner"
OWNER_VERSION = "postgres-advisory-v1"
ACTIVE = ("accepted", "running")


class AdmissionBusy(RuntimeError):
    """Another job or an unresolved legacy job occupies ingestion capacity."""


class OwnershipLost(RuntimeError):
    """The original lock-owning database session is no longer usable."""


def lock_key(scope: str, identity: str) -> int:
    """Stable signed bigint, disjoint application namespaces, never hash()."""
    digest = blake2b(
        f"rag-foundry:{scope}:{identity}".encode(), digest_size=8,
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


class AdvisoryGuard:
    """One dedicated DBAPI connection; never transparently reconnect a guard.

    engine.raw_connection() is detached from its pool immediately, so close()
    physically ends the session (also on exceptions) instead of leaking locks
    to another request. Calls are sequential; transfer to a worker only after
    the accepting request has finished using this object.
    """

    def __init__(self, engine: Engine):
        connection = engine.raw_connection()
        if connection is None:
            raise OwnershipLost("Could not acquire ownership database connection")
        self._connection = connection
        self._connection.detach()
        # SQLAlchemy's pool proxy does not forward assignment to the driver.
        try:
            self._connection.driver_connection.autocommit = True
        except BaseException:
            self._connection.close()
            raise
        self._closed = False

    def try_lock(self, scope: str, identity: str) -> bool:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_lock(%s)", (lock_key(scope, identity),),
                )
                return bool(cursor.fetchone()[0])
        except Exception as exc:
            raise OwnershipLost("Ingestion ownership database connection lost") from exc

    def check(self) -> None:
        if self._closed:
            raise OwnershipLost("Ingestion ownership already released")
        try:
            with self._connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            raise OwnershipLost("Ingestion ownership database connection lost") from exc

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def reserve_ingestion(engine: Engine, ingestion_id: UUID) -> AdvisoryGuard:
    """Reserve one global active job BEFORE reading upload bytes/creating a row.

    One slot intentionally matches the present single-GPU deployment. No
    per-process configurable capacities that could disagree across replicas.
    Historical active rows conservatively block new work until reconciled.
    """
    guard = AdvisoryGuard(engine)
    try:
        if not guard.try_lock("admission", "global-single-job"):
            raise AdmissionBusy("Ingestion capacity occupied; retry later")
        with Session(engine) as session:
            active_id = session.scalar(select(IngestionRequest.ingestion_id).where(
                IngestionRequest.status.in_(ACTIVE),
            ).limit(1))
            if active_id is not None:
                raise AdmissionBusy("Active ingestion requires completion or recovery")
        if not guard.try_lock("attempt", str(ingestion_id)):
            raise AdmissionBusy("Ingestion attempt already owned")
        return guard
    except BaseException:
        guard.close()
        raise


def owned_metadata(metadata: dict) -> dict:
    # Never trust a user-supplied ownership marker.
    return {**metadata, OWNER_KEY: OWNER_VERSION}


def reconcile_ingestions(engine: Engine, *, include_legacy: bool = False) -> int:
    """Fail ownerless active attempts; retain all partial artifacts and vectors.

    include_legacy is an explicit maintenance action after stopping old workers,
    never an automatic assumption made when another API process starts.
    Keyset pages avoid loading an unbounded history of orphan jobs.
    """
    recovered = 0
    last_id = None
    while True:
        query = select(IngestionRequest.ingestion_id).where(
            IngestionRequest.status.in_(ACTIVE),
        ).order_by(IngestionRequest.ingestion_id).limit(100)
        if last_id is not None:
            query = query.where(IngestionRequest.ingestion_id > last_id)
        with Session(engine) as session:
            ids = list(session.scalars(query))
        if not ids:
            return recovered
        for ingestion_id in ids:
            with AdvisoryGuard(engine) as guard:
                if not guard.try_lock("attempt", str(ingestion_id)):
                    continue
                with Session(engine) as session:
                    request = session.scalar(select(IngestionRequest).where(
                        IngestionRequest.ingestion_id == ingestion_id,
                    ).with_for_update())
                    if request is None or request.status not in ACTIVE:
                        continue
                    managed = (request.ingestion_metadata or {}).get(OWNER_KEY)
                    if managed != OWNER_VERSION and not include_legacy:
                        continue
                    StatusManager(session).mark_failed(
                        ingestion_id,
                        error="Ingestion interrupted: database ownership is absent; "
                        "partial data retained, no automatic retry",
                    )
                    recovered += 1
        last_id = ids[-1]
