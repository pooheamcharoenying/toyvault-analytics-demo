"""Thin LINE Messaging API client: signature verification + reply/push.

- ``verify_signature`` — validate the ``X-Line-Signature`` header against the raw
  request body with the channel secret (HMAC-SHA256, base64). This is how the
  public webhook authenticates that a request really came from LINE.
- ``reply`` — answer within the webhook's reply token (free; ~1 min window).
- ``push`` — send a message any time to a user id (used for slow agent answers
  that would miss the reply-token window).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_API = "https://api.line.me/v2/bot/message"


def verify_signature(body: bytes, signature: str) -> bool:
    secret = get_settings().LINE_CHANNEL_SECRET
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def is_configured() -> bool:
    s = get_settings()
    return bool(s.LINE_CHANNEL_SECRET and s.LINE_CHANNEL_ACCESS_TOKEN)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_settings().LINE_CHANNEL_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


def _chunks(text: str, size: int = 4900):
    """LINE caps a text message at 5000 chars — split long answers."""
    text = text or ""
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def reply(reply_token: str, text: str) -> None:
    try:
        messages = [{"type": "text", "text": t} for t in _chunks(text)][:5]
        httpx.post(f"{_API}/reply", headers=_headers(),
                   json={"replyToken": reply_token, "messages": messages}, timeout=15)
    except Exception:
        logger.exception("LINE reply failed")


def _send_push(user_id: str, msgs: list) -> bool:
    """POST a push, retrying transient failures (LINE 429 / 5xx) so a momentary
    hiccup doesn't silently drop the message. Returns True on delivery. We retry
    only on statuses that mean 'not delivered' — never on an exception (unknown
    delivery state), to avoid duplicate sends. Max 5 messages per LINE limit."""
    msgs = [m for m in (msgs or []) if m][:5]
    if not msgs:
        return True
    for attempt in range(3):
        try:
            r = httpx.post(f"{_API}/push", headers=_headers(),
                           json={"to": user_id, "messages": msgs}, timeout=15)
            if r.status_code == 200:
                return True
            if r.status_code == 429 or 500 <= r.status_code < 600:   # transient
                logger.warning("LINE push %s (attempt %d/3): %s",
                               r.status_code, attempt + 1, (r.text or "")[:200])
                time.sleep(0.8)
                continue
            logger.error("LINE push HTTP %s: %s", r.status_code, (r.text or "")[:300])
            return False   # 4xx (bad request) — retrying won't help
        except Exception:
            logger.exception("LINE push exception")
            return False   # unknown delivery state — don't retry (could duplicate)
    return False


def push(user_id: str, text: str) -> bool:
    return _send_push(user_id, [{"type": "text", "text": t} for t in _chunks(text)])


def push_messages(user_id: str, messages: list) -> bool:
    """Push already-built LINE message objects (text, flex, …). Returns True on
    success — the caller falls back to a plain-text push if a rich message (e.g.
    an oversized Flex card) is rejected, so a rendering issue never leaves the
    user with total silence."""
    return _send_push(user_id, messages)


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {get_settings().LINE_CHANNEL_ACCESS_TOKEN}"}


def get_profile(user_id: str) -> dict | None:
    """Fetch a LINE user's public profile — {displayName, pictureUrl, userId, …}.
    Used to show *which* LINE account a ToyVault user has linked. None on failure."""
    if not user_id or not is_configured():
        return None
    try:
        r = httpx.get(f"https://api.line.me/v2/bot/profile/{user_id}",
                      headers=_auth_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
        logger.warning("LINE get_profile %s -> %s: %s", user_id, r.status_code, (r.text or "")[:200])
    except Exception:
        logger.exception("LINE get_profile failed")
    return None


def get_bot_info() -> dict | None:
    """Fetch the bot's own Official Account identity — {basicId, displayName,
    pictureUrl, …}. Lets the web app always show the correct name/ID/QR for the
    AI Assist bot. None on failure."""
    if not is_configured():
        return None
    try:
        r = httpx.get("https://api.line.me/v2/bot/info", headers=_auth_headers(), timeout=10)
        if r.status_code == 200:
            return r.json()
        logger.warning("LINE get_bot_info -> %s: %s", r.status_code, (r.text or "")[:200])
    except Exception:
        logger.exception("LINE get_bot_info failed")
    return None


def start_loading(user_id: str, seconds: int = 60) -> None:
    """Show LINE's loading animation (the 'typing…' dots) in the 1:1 chat while the
    agent works — it auto-dismisses when we send the reply, or after `seconds`.
    `seconds` must be a multiple of 5, in 5–60."""
    try:
        s = max(5, min(60, (int(seconds) // 5) * 5))
        httpx.post("https://api.line.me/v2/bot/chat/loading/start", headers=_headers(),
                   json={"chatId": user_id, "loadingSeconds": s}, timeout=10)
    except Exception:
        logger.exception("LINE loading start failed")
