"""AI Assist chat endpoint — the ToyVault business assistant.

`def` (not `async def`) on purpose: the agent loop makes blocking OpenAI calls,
so FastAPI runs it in a threadpool and the event loop stays free. Auth is enforced
at include_router() in app/main.py, like the other routers.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel

from app.assistant.agent import run_agent
from app.assistant.tools import TOOL_SPECS
from app.assistant import threads
from app.auth import tokens

router = APIRouter(tags=["assistant"])


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


@router.post("/assistant/chat", summary="Ask the ToyVault AI assistant a question (stateless)")
def assistant_chat(req: ChatRequest) -> dict:
    """Stateless one-shot: returns the reply plus the tool-call trace. For a
    persistent conversation use the thread endpoints below."""
    return run_agent(req.message, req.history)


# --- Persistent per-user threads --------------------------------------------

def _current_user(token: str) -> str:
    payload = tokens.verify(token or "")
    if not payload:
        raise HTTPException(status_code=401, detail="Not signed in.")
    return payload["sub"]


@router.get("/assistant/threads", summary="List the current user's chat threads")
def list_threads(x_session_token: str = Header(default="")) -> dict:
    return {"threads": threads.list_for(_current_user(x_session_token))}


@router.post("/assistant/threads", summary="Create an empty chat thread")
def create_thread(body: dict = Body(default={}), x_session_token: str = Header(default="")) -> dict:
    user = _current_user(x_session_token)
    tid = threads.create(user, (body or {}).get("title") or "New chat")
    return {"thread_id": tid, "title": "New chat"}


@router.get("/assistant/threads/{tid}", summary="Get a thread's messages")
def get_thread(tid: str, x_session_token: str = Header(default="")) -> dict:
    t = threads.get(_current_user(x_session_token), tid)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return t


@router.post("/assistant/threads/{tid}/messages", summary="Send a message in a thread (runs the agent)")
def post_message(tid: str, body: dict = Body(...), x_session_token: str = Header(default="")) -> dict:
    """Append the user's message, run the agent with the thread's prior history,
    persist both the question and the answer, and return the reply. Pass
    ``tid='new'`` to start a fresh thread (auto-titled from the first message)."""
    user = _current_user(x_session_token)
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="message is required")

    created = False
    if tid == "new":
        tid = threads.create(user, threads.title_from(message))
        created = True
    elif not threads.owns(user, tid):
        raise HTTPException(status_code=404, detail="Thread not found.")

    result = run_agent(message, threads.history(user, tid))
    threads.append(user, tid, "user", message)
    asst_data = {"version": result.get("version")}
    if result.get("datasets"):
        asst_data["datasets"] = result["datasets"]
    threads.append(user, tid, "assistant", result.get("reply") or "", data=asst_data)
    return {"thread_id": tid, "created": created, **result}


@router.patch("/assistant/threads/{tid}", summary="Rename a thread")
def rename_thread(tid: str, body: dict = Body(...), x_session_token: str = Header(default="")) -> dict:
    user = _current_user(x_session_token)
    if not threads.owns(user, tid):
        raise HTTPException(status_code=404, detail="Thread not found.")
    threads.rename(user, tid, body.get("title", ""))
    return {"status": "ok"}


@router.delete("/assistant/threads/{tid}", summary="Delete a thread")
def delete_thread(tid: str, x_session_token: str = Header(default="")) -> dict:
    threads.delete(_current_user(x_session_token), tid)
    return {"status": "ok"}


@router.get("/assistant/tools", summary="List the tools the assistant can call (debug)")
def assistant_tools() -> dict:
    """Names + descriptions of the registered tools — for debugging/inspection."""
    return {
        "count": len(TOOL_SPECS),
        "tools": [
            {"name": s["function"]["name"], "description": s["function"]["description"]}
            for s in TOOL_SPECS
        ],
    }
