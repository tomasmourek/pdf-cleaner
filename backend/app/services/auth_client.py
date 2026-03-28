from fastapi import HTTPException, Header
from jose import JWTError, jwt
from typing import Optional
from ..core.config import settings


def _decode(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            raise JWTError("Not access token")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Neplatný nebo expirovaný přístupový token.")


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Chybí přístupový token.")
    payload = _decode(authorization.removeprefix("Bearer ").strip())
    return {"id": payload["sub"], "role": payload.get("role", "user"), "plan": payload.get("plan", "free")}


async def require_plan(current_user: dict, plan: str) -> None:
    order = {"free": 0, "pro": 1, "business": 2}
    if order.get(current_user.get("plan", "free"), 0) < order.get(plan, 999):
        raise HTTPException(status_code=403, detail=f"Vyžaduje plán {plan.upper()} nebo vyšší.")
