# llm_service/src/api/v1/admin.py
"""
WP-M7: admin surface for the runtime model policy. Write-only auth: the
GET side of policy state rides on GET /v1/models (`overridden_by_policy`
per alias) with no auth, per the user's explicit decision -- only the
WRITE endpoints below are gated.

Auth is a single shared secret (LLM_ADMIN_SECRET, env-only, same trust
model as every other credential in this service) sent as the
X-Admin-Secret header, compared with hmac.compare_digest to avoid a
timing side-channel. Fails CLOSED: if LLM_ADMIN_SECRET is unset, writes
are refused with 503 rather than silently accepting unauthenticated
requests -- a fresh clone/deploy that hasn't set the var never has an
open write endpoint.
"""
import hmac
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.core import model_policy
from src.core.model_registry import get_registry, reset_registry

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class SetSlotRequest(BaseModel):
    model: str


def _check_admin_secret(x_admin_secret: str | None) -> None:
    expected = os.getenv("LLM_ADMIN_SECRET")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Admin writes are disabled: LLM_ADMIN_SECRET is not set.",
        )
    if not x_admin_secret or not hmac.compare_digest(x_admin_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Secret")


@router.put("/policy/{slot}")
async def set_slot(
    slot: str,
    body: SetSlotRequest,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict:
    _check_admin_secret(x_admin_secret)

    # Validated against resolve() only -- the same check every other
    # model string in this service goes through (alias / raw LiteLLM
    # string / <endpoint>/<model>). Never validated against the WP-M6
    # discovered catalog, which is advisory/observational and may be
    # stale, incomplete, or briefly unreachable.
    try:
        get_registry().resolve(None, body.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    model_policy.write_slot(slot, body.model)
    reset_registry()  # WP-M7 runtime policy refresh
    return {"slot": slot, "model": body.model, "models": get_registry().describe()}


@router.delete("/policy/{slot}")
async def clear_slot(
    slot: str,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict:
    _check_admin_secret(x_admin_secret)
    model_policy.clear_slot(slot)
    reset_registry()
    return {"slot": slot, "cleared": True, "models": get_registry().describe()}
