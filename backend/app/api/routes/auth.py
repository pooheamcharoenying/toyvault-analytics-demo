"""User authentication endpoints.

- ``POST /api/auth/login``  — verify username/password, return a session token.
- ``GET  /api/auth/me``     — validate a session token, return the user.
- Admin-only user management under ``/api/auth/users``.

These sit behind the BFF's service Basic auth (like every other router); the
per-USER check happens inside. The session token is passed in the
``X-Session-Token`` header by the BFF.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Header, HTTPException

from app.auth import store, tokens

router = APIRouter(tags=["auth"])


def _require_session(token: str) -> dict:
    payload = tokens.verify(token or "")
    if not payload:
        raise HTTPException(status_code=401, detail="Not signed in or session expired.")
    return payload


def _require_admin(token: str) -> dict:
    payload = _require_session(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return payload


@router.post("/auth/login", summary="Sign in with username + password")
def login(body: dict = Body(...)) -> dict:
    if not store.is_available():
        raise HTTPException(status_code=503, detail="User store is not configured.")
    user = store.verify_credentials(body.get("username", ""), body.get("password", ""))
    if not user:
        # Deliberately generic — never reveal which field was wrong.
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = tokens.issue(user["username"], user["role"], user["display_name"])
    return {"token": token, "user": user}


@router.get("/auth/me", summary="Validate the current session")
def me(x_session_token: str = Header(default="")) -> dict:
    p = _require_session(x_session_token)
    return {"user": {"username": p["sub"], "role": p.get("role", "user"),
                     "display_name": p.get("name")}}


@router.post("/auth/change_password", summary="Change your own password")
def change_password(body: dict = Body(...), x_session_token: str = Header(default="")) -> dict:
    p = _require_session(x_session_token)
    try:
        store.change_password(p["sub"], body.get("current_password", ""), body.get("new_password", ""))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok"}


@router.get("/auth/users", summary="List users (admin)")
def list_users(x_session_token: str = Header(default="")) -> dict:
    _require_admin(x_session_token)
    return {"users": store.list_users()}


@router.post("/auth/users", summary="Create/update a user (admin)")
def create_user(body: dict = Body(...), x_session_token: str = Header(default="")) -> dict:
    _require_admin(x_session_token)
    try:
        uname = store.create_user(
            body.get("username", ""), body.get("password", ""),
            body.get("display_name"), body.get("role", "user"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok", "username": uname}


@router.delete("/auth/users/{username}", summary="Delete a user (admin)")
def delete_user(username: str, x_session_token: str = Header(default="")) -> dict:
    admin = _require_admin(x_session_token)
    if store._norm(username) == admin["sub"]:
        raise HTTPException(status_code=422, detail="You cannot delete your own account.")
    store.delete_user(username)
    return {"status": "ok"}
