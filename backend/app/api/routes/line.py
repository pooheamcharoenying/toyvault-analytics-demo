"""LINE Messaging API routes.

- ``POST /api/line/webhook`` — PUBLIC (no Basic auth); LINE authenticates by
  signature. It acks 200 immediately and processes each message in the
  background (the agent takes 20–40s), pushing the answer back.
- ``POST /api/line/link_code`` — behind Basic auth + session; the signed-in user
  generates a one-time code to link their LINE account.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.assistant.agent import run_agent
from app.assistant.version import BOT_VERSION
from app.assistant import threads
from app.auth import tokens
from app.line import bindings, client
# Table rendering (plain-text + Flex Message) lives in app.line.flex; re-exported
# here so existing imports of these names from this module keep working.
from app.line.flex import (  # noqa: F401
    _COL_LABELS, _humanize_col, _abbrev_money, _fmt_val, _presentation_to_text,
    build_table_flex, build_download_flex, _external_browser_url,
)

logger = logging.getLogger(__name__)

webhook_router = APIRouter(tags=["line"])   # mounted WITHOUT Basic auth
api_router = APIRouter(tags=["line"])        # mounted WITH Basic auth

_LINK_HELP = (
    "Hi! To use ToyVault AI Assist on LINE:\n"
    "1) Open the ToyVault web app and sign in\n"
    "2) Top-right: your name → \"Link LINE\"\n"
    "3) Send me the 6-character code shown there."
)

# Text commands the bot intercepts BEFORE running the agent (exact match, trimmed
# and lower-cased). Kept as exact phrases so a normal question like "how do I reset
# stock?" is NOT treated as a command.
_RESET_COMMANDS = {
    "/reset", "/new", "/newchat", "/clear",
    "reset", "new chat", "new conversation", "clear history", "start over",
    "รีเซ็ต", "เริ่มใหม่", "เริ่มต้นใหม่", "แชทใหม่", "คุยใหม่", "ล้างประวัติ", "ล้างความจำ",
}
_HELP_COMMANDS = {"/help", "help", "?", "ช่วยเหลือ", "วิธีใช้", "คำสั่ง"}

_RESET_REPLY = (
    "🆕 เริ่มแชทใหม่แล้วครับ — ล้างความจำการสนทนาเดิมทั้งหมด พร้อมตอบคำถามใหม่\n"
    "New chat session started — previous context cleared. Ask me anything!"
)
_HELP_TEXT = (
    "🤖 ToyVault AI Assist\n"
    "ถามข้อมูลธุรกิจได้เลย เช่น ยอดขาย แบรนด์ สต็อก สาขา / Ask about revenue, brands, stock, locations.\n\n"
    "คำสั่ง / Commands:\n"
    "• \"ขอเป็น excel\" — ดาวน์โหลดตารางเป็นไฟล์ / download a table as a file\n"
    "• /reset — เริ่มบทสนทนาใหม่ ล้างความจำ / start a fresh conversation\n"
    "• /help — แสดงคำสั่งนี้ / show this help"
)


def _normalize_cmd(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _build_line_messages(result: dict, version: str) -> list:
    """Build the LINE message list for an agent answer: a text message (narrative
    + download link), then the table as a Flex card when it fits a phone — else
    the table folded into the text. The version stamp goes in the Flex footer when
    a card is shown, otherwise at the end of the text."""
    reply = result.get("reply") or "(no answer)"
    datasets = result.get("datasets") or []
    dl = result.get("download") or {}

    flex = build_table_flex(datasets[0], version=version) if datasets else None

    text_part = reply
    if not flex:                     # no card -> fold the table + version into text
        if datasets:
            text_part += "\n\n" + _presentation_to_text(datasets[0])
        text_part += f"\n\n— ToyVault AI v{version}"

    messages = [{"type": "text", "text": ch} for ch in client._chunks(text_part)]
    if flex:
        messages.append(flex)        # version is in the card footer
    dl_flex = build_download_flex(dl)
    if dl_flex:
        messages.append(dl_flex)     # a tap-to-download button (LINE can't attach files)
    return messages[:5]              # LINE allows at most 5 messages per push


def _plain_text_reply(result: dict, version: str) -> str:
    """A pure-text version of the answer — the fallback when the rich (Flex) push
    is rejected, so the user always gets the answer instead of silence."""
    parts = [result.get("reply") or "(no answer)"]
    datasets = result.get("datasets") or []
    if datasets:
        parts.append(_presentation_to_text(datasets[0]))
    dl = result.get("download") or {}
    if dl.get("url"):
        parts.append(f"📎 {dl.get('filename', 'file')}\n{_external_browser_url(dl['url'])}")
    parts.append(f"— ToyVault AI v{version}")
    return "\n\n".join(parts)


def _process_event(event: dict) -> None:
    """Runs in the background after the webhook has acked LINE."""
    try:
        line_uid = event["source"]["userId"]
        text = (event["message"]["text"] or "").strip()
        reply_token = event.get("replyToken")
    except Exception:
        logger.exception("malformed LINE event")
        return

    username = bindings.get_username(line_uid)
    if not username:
        linked = bindings.consume_link_code(text)
        if linked:
            bindings.bind(line_uid, linked)
            client.reply(reply_token, f"✅ Linked to {linked}. Ask me anything about the business — e.g. \"how's the business doing?\"")
        else:
            client.reply(reply_token, _LINK_HELP)
        return

    # Text commands (handled instantly, no agent run). Use push (not the reply
    # token) so the acknowledgement is guaranteed, and never let a reset error
    # swallow it.
    cmd = _normalize_cmd(text)
    if cmd in _RESET_COMMANDS:
        try:
            bindings.reset_thread(line_uid, username)
        except Exception:
            logger.exception("LINE /reset: reset_thread failed")
        client.push(line_uid, _RESET_REPLY)
        return
    if cmd in _HELP_COMMANDS:
        client.push(line_uid, _HELP_TEXT)
        return

    # Bound staff member → run the same agent, with this LINE conversation's memory.
    client.start_loading(line_uid)   # show the "typing…" animation while we think (20–40s)
    tid = bindings.get_or_create_thread(line_uid, username)
    history = threads.history(username, tid) if tid else []
    result = run_agent(text, history, platform="line")
    version = result.get("version") or BOT_VERSION
    datasets = result.get("datasets") or []
    if tid:
        asst_data = {"version": version}
        if datasets:
            asst_data["datasets"] = datasets
        threads.append(username, tid, "user", text)
        threads.append(username, tid, "assistant", result.get("reply") or "", data=asst_data)
    # push (not reply): the agent is too slow for the reply-token window. If the
    # rich push (Flex card) is rejected, fall back to plain text so the user is
    # never left with total silence.
    if not client.push_messages(line_uid, _build_line_messages(result, version)):
        client.push(line_uid, _plain_text_reply(result, version))


@webhook_router.post("/line/webhook", summary="LINE Messaging API webhook (public)")
async def line_webhook(request: Request, background_tasks: BackgroundTasks,
                       x_line_signature: str = Header(default="")) -> dict:
    body = await request.body()
    if not client.verify_signature(body, x_line_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    try:
        payload = json.loads(body or b"{}")
    except Exception:
        return {"ok": True}
    for event in payload.get("events", []):
        if event.get("type") == "message" and (event.get("message") or {}).get("type") == "text":
            background_tasks.add_task(_process_event, event)
    return {"ok": True}


@api_router.post("/line/link_code", summary="Generate a one-time LINE link code")
def line_link_code(x_session_token: str = Header(default="")) -> dict:
    p = tokens.verify(x_session_token or "")
    if not p:
        raise HTTPException(status_code=401, detail="Not signed in.")
    code = bindings.create_link_code(p["sub"])
    if not code:
        raise HTTPException(status_code=503, detail="LINE linking is unavailable (no database).")
    return {"code": code, "expires_minutes": 15}
