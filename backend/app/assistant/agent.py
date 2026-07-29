"""The agent loop: user question -> OpenAI (with read tools) -> grounded answer.

Deliberately small. OpenAI decides which read tools to call; we execute them
in-process against the app's own analytics functions, feed the results back, and
loop until the model answers or we hit the step cap. Every turn is written to a
lightweight ``ai_request`` audit (in Mongo, non-fatal) so a logging failure never
costs the user their answer.
"""
from __future__ import annotations

import json
import logging
import time

from app.core.config import get_settings
from app.assistant.prompts import (
    PROMPT_NAME, PROMPT_VERSION, SYSTEM_PROMPT, LINE_STYLE_ADDENDUM,
)
from app.assistant.version import BOT_VERSION
from app.assistant.tools import TOOL_SPECS, run_tool, tool_result_to_message

logger = logging.getLogger(__name__)

#: Cap on rows attached per dataset (kept off the model, sent straight to the UI).
MAX_DATASET_ROWS = 500

#: Cap on rows of any single list handed BACK TO THE MODEL in a tool result. The
#: model only needs enough rows to reason and the total count — the full list is
#: captured separately for the UI (present_table). Without this, a 500-row result
#: re-sent on every reasoning step blows past the model's context window
#: (context_length_exceeded).
MODEL_ROW_CAP = 50

#: Row fields, in preference order, that make a human-readable row label. A table
#: with only numeric columns is unreadable (especially on LINE, which has no
#: headers), so we always surface one of these as the first column.
_LABEL_FIELDS = (
    "item_name", "name", "location", "brand", "channel", "item_code",
    "title", "period", "month",
)


def _extract_dataset(result: dict):
    """Pull the primary table (largest list-of-objects) out of a tool result, so
    the UI can render the COMPLETE list + CSV itself — the model reliably
    abbreviates long tables, so we never depend on its text for the full data."""
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    data = result.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[:MAX_DATASET_ROWS]
    if not isinstance(data, dict):
        return None
    best = None
    for v in data.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            if best is None or len(v) > len(best):
                best = v
    return best[:MAX_DATASET_ROWS] if best and len(best) > 1 else None


def _extract_datasets(result: dict) -> list[list]:
    """ALL candidate row-lists in a tool result — a multi-list result (e.g.
    location_product_mix returns top-items-by-onhand, top-sellers, non-movers,
    top-brands…) gives several. present_table then picks whichever one matches the
    columns the model asked for, instead of blindly rendering the largest."""
    if not isinstance(result, dict) or not result.get("ok"):
        return []
    data = result.get("data")
    out: list[list] = []
    if isinstance(data, list) and data and isinstance(data[0], dict):
        out.append(data[:MAX_DATASET_ROWS])
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                out.append(v[:MAX_DATASET_ROWS])
    return out


def _select_dataset(candidates: list[list], requested_cols, sort_by=None, sort_desc=True):
    """Choose which candidate list present_table should render.

    Primary: the list whose fields cover the MOST of the requested columns (so a
    request for item-level on-hand columns renders the item list, not the brand
    list that merely happened to be largest).

    Tie-break when several lists have the SAME columns (e.g. location_product_mix
    returns top-sellers, top-by-on-hand-value and non-movers all with identical
    fields): prefer the list whose ``sort_by`` values are most EXTREME in the sort
    direction — that's the list the user is actually ranking for. Without this, a
    "highest on-hand value" request could render the top-sellers list (low on-hand)
    just because it was equal-or-larger. Falls back to size."""
    cands = [c for c in candidates if c]
    if not cands:
        return None
    req_set = set(requested_cols or [])
    if not req_set:
        return max(cands, key=len)
    best = max(len(req_set & set(c[0].keys())) for c in cands)
    matching = [c for c in cands if len(req_set & set(c[0].keys())) == best]
    if len(matching) == 1:
        return matching[0]
    if sort_by:
        def extreme(rows):
            vals = [r.get(sort_by) for r in rows
                    if isinstance(r.get(sort_by), (int, float)) and not isinstance(r.get(sort_by), bool)]
            if not vals:
                return float("-inf")
            return max(vals) if sort_desc else -min(vals)
        return max(matching, key=lambda rows: (extreme(rows), len(rows)))
    return max(matching, key=len)


def _cap_list(v):
    """If v is a long list of records, return (capped_list, original_len); else (v, None)."""
    if isinstance(v, list) and len(v) > MODEL_ROW_CAP and v and isinstance(v[0], dict):
        return v[:MODEL_ROW_CAP], len(v)
    return v, None


def _truncate_for_model(result: dict) -> dict:
    """Cap large lists in a tool result before it enters the model's context.

    The model gets the first ``MODEL_ROW_CAP`` rows plus the true total, which is
    enough to rank/summarise; the COMPLETE list is still captured by
    ``_extract_dataset`` for the on-screen table + CSV. This is the guard against
    ``context_length_exceeded`` from re-sending huge tool payloads every step."""
    if not isinstance(result, dict):
        return result
    data = result.get("data")
    if data is None:
        return result
    notes = []
    out = dict(result)
    if isinstance(data, list):
        capped, total = _cap_list(data)
        out["data"] = capped
        if total:
            notes.append(f"list capped to first {MODEL_ROW_CAP} of {total} rows")
    elif isinstance(data, dict):
        new_data = dict(data)
        for k, v in data.items():
            capped, total = _cap_list(v)
            if total:
                new_data[k] = capped
                notes.append(f"'{k}' capped to first {MODEL_ROW_CAP} of {total} rows")
        out["data"] = new_data
    if notes:
        out["_truncated"] = ("; ".join(notes)
                             + " — the user is shown the COMPLETE list via present_table, "
                               "so you can present all of it; use these rows to reason.")
    return out


def _apply_presentation(args: dict, rows):
    """Render the model's `present_table` directive against the most recent dataset:
    pick the columns it chose (validated against real fields), sort, and cap rows.
    Returns {title, columns, rows, total_available} or None if there's no data."""
    if not rows:
        return None
    fields = list(rows[0].keys())
    cols = [c for c in (args.get("columns") or []) if c in fields] or fields
    # Always surface a human-readable label column, FIRST — the model sometimes
    # picks only numeric columns (e.g. on-hand qty + value), which reads as naked
    # numbers with no idea what they name. Helps the web table too.
    label = next((c for c in cols if c in _LABEL_FIELDS), None)
    if label:
        cols = [label] + [c for c in cols if c != label]
    else:
        for lf in _LABEL_FIELDS:
            if lf in fields:
                cols = [lf] + cols
                break
    data = list(rows)
    sort_by = args.get("sort_by")
    if sort_by and sort_by in fields:
        try:
            data.sort(key=lambda r: (r.get(sort_by) is None, r.get(sort_by)),
                      reverse=bool(args.get("sort_desc", True)))
        except TypeError:
            pass  # mixed types — leave the tool's own order
    max_rows = args.get("max_rows")
    total = len(data)
    if isinstance(max_rows, int) and max_rows > 0:
        data = data[:max_rows]
    projected = [{c: r.get(c) for c in cols} for r in data]
    return {"title": args.get("title"), "columns": cols, "rows": projected, "total_available": total}


def _history_messages(history) -> list[dict]:
    """Prior turns as clean OpenAI messages — role + content only. Drops the
    persisted `data`/`datasets` payloads (UI-only) so they never re-enter the
    model context and inflate token count."""
    return [{"role": h["role"], "content": h.get("content") or ""}
            for h in (history or []) if h.get("role") in ("user", "assistant")]


def _system_prompt(platform: str) -> str:
    """The system prompt for a platform. LINE gets a plain-text formatting
    addendum appended; the analyst behaviour is otherwise identical."""
    return SYSTEM_PROMPT + (LINE_STYLE_ADDENDUM if platform == "line" else "")


# --- Context-window safety net (bot v1.0.2) --------------------------------

#: Tokens reserved for the model's reply + slack in our (approximate) estimate.
#: We trim to (context_limit - this), so the window is never filled to the brim.
RESPONSE_RESERVE_TOKENS = 16_000

#: Left in place of a shrunk tool result — tells the model data was dropped so it
#: can re-fetch rather than answer over a gap.
_TRIM_NOTE = ("[earlier tool result omitted to fit the context window — "
              "call the tool again if you still need those rows]")

#: Friendly, actionable replies — users must never see a raw API error.
_TOO_MUCH_DATA_REPLY = (
    "That question pulls in more data than I can process in one go. Try narrowing "
    "it — a single brand, one location, a shorter time period, or fewer items — "
    "and I'll get it for you.")
_GENERIC_ERROR_REPLY = (
    "Sorry, I hit a problem reaching the AI service just now. Please try again in "
    "a moment.")


class _ContextTooLarge(Exception):
    """A request won't fit even the largest available context window."""


def _estimate_tokens(messages: list[dict], tools=None) -> int:
    """Cheap, dependency-free, deliberately CONSERVATIVE token estimate — better to
    over-count and trim early than under-count and hit a 400. ~3.5 chars/token for
    ASCII/JSON plus per-message overhead; the generous RESPONSE_RESERVE absorbs the
    error for denser text (e.g. Thai). If the estimate is still off, the API-error
    backstop in ``_create_fitted`` catches it."""
    chars = 0
    for m in messages:
        chars += len(str(m.get("content") or ""))
        for tc in (m.get("tool_calls") or []):
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            chars += len(str(fn.get("name", ""))) + len(str(fn.get("arguments", "") or ""))
    if tools:
        try:
            chars += len(json.dumps(tools, default=str))
        except Exception:
            pass
    return int(chars / 3.5) + 4 * len(messages)


def _send_budget(context_limit: int) -> int:
    return max(4_000, int(context_limit) - RESPONSE_RESERVE_TOKENS)


def _shrink_tool_msg(m: dict) -> dict:
    """Replace a tool message's content with the breadcrumb, keeping its
    tool_call_id — removing the message would orphan the assistant tool_call and
    make the API 400."""
    if m.get("role") == "tool" and len(str(m.get("content") or "")) > len(_TRIM_NOTE):
        return {**m, "content": _TRIM_NOTE}
    return m


def _is_context_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return ("context_length_exceeded" in s or "maximum context length" in s
            or "context window" in s or "too many tokens" in s)


def _fit_context(system_msg, history, current_msg, run_msgs, budget, tools):
    """Assemble [system] + history + [current question] + this-run messages and
    trim least-valuable-first until it fits ``budget``. Returns (messages, fits).

    Never touches the system prompt or the current question. Drops the OLDEST
    conversation turns first; then SHRINKS the oldest tool results (keeping the
    newest intact as long as possible); last resort, shrinks the newest too. Tool
    results are shrunk in place (never removed) to keep tool_call pairing valid."""
    hist = list(history)
    run = list(run_msgs)

    def assemble(h, r):
        return [system_msg, *h, current_msg, *r]

    def over(h, r):
        return _estimate_tokens(assemble(h, r), tools) > budget

    if not over(hist, run):
        return assemble(hist, run), True

    # 1) drop oldest conversation turns
    while hist and over(hist, run):
        hist = hist[1:]
    if not over(hist, run):
        return assemble(hist, run), True

    # 2) shrink oldest tool results; keep the newest intact while we can
    tool_idx = [i for i, m in enumerate(run) if m.get("role") == "tool"]
    for i in tool_idx[:-1]:
        run[i] = _shrink_tool_msg(run[i])
        if not over(hist, run):
            return assemble(hist, run), True

    # 3) last resort: shrink the newest tool result too
    if tool_idx:
        run[tool_idx[-1]] = _shrink_tool_msg(run[tool_idx[-1]])

    return assemble(hist, run), not over(hist, run)


def _create_fitted(client, settings, system_msg, history, current_msg, run_msgs):
    """Fit to the default model's budget; if it still won't fit, escalate to the
    bigger-context model; if even that won't fit, raise ``_ContextTooLarge``. An
    API context error (our estimate under-counted) is a backstop that also
    escalates. Returns (response, model_used)."""
    fitted, fits = _fit_context(system_msg, history, current_msg, run_msgs,
                                _send_budget(settings.OPENAI_CONTEXT_LIMIT), TOOL_SPECS)
    model = settings.OPENAI_MODEL
    if not fits and settings.OPENAI_MODEL_LARGE:
        fitted_l, fits_l = _fit_context(system_msg, history, current_msg, run_msgs,
                                        _send_budget(settings.OPENAI_LARGE_CONTEXT_LIMIT), TOOL_SPECS)
        if fits_l:
            logger.info("assistant: request exceeded %s context; escalating to %s",
                        settings.OPENAI_MODEL, settings.OPENAI_MODEL_LARGE)
            fitted, model, fits = fitted_l, settings.OPENAI_MODEL_LARGE, True
    if not fits:
        raise _ContextTooLarge()

    try:
        resp = client.chat.completions.create(
            model=model, messages=fitted, tools=TOOL_SPECS, tool_choice="auto")
        return resp, model
    except Exception as exc:
        if not _is_context_error(exc):
            raise
        # Estimate under-counted and the API rejected on length. Escalate once.
        if model != settings.OPENAI_MODEL_LARGE and settings.OPENAI_MODEL_LARGE:
            logger.info("assistant: API context error on %s; retrying on %s", model,
                        settings.OPENAI_MODEL_LARGE)
            fitted_l, _ = _fit_context(system_msg, history, current_msg, run_msgs,
                                       _send_budget(settings.OPENAI_LARGE_CONTEXT_LIMIT), TOOL_SPECS)
            try:
                resp = client.chat.completions.create(
                    model=settings.OPENAI_MODEL_LARGE, messages=fitted_l,
                    tools=TOOL_SPECS, tool_choice="auto")
                return resp, settings.OPENAI_MODEL_LARGE
            except Exception as exc2:
                if _is_context_error(exc2):
                    raise _ContextTooLarge()
                raise
        raise _ContextTooLarge()


def run_agent(message: str, history: list[dict] | None = None,
              platform: str = "web") -> dict:
    """Answer ``message`` with the grounded tool-calling agent.

    ``platform`` selects the FORMAT of the final answer only — the tools, model
    and analysis are identical. ``"web"`` (default) renders rich tables in the UI;
    ``"line"`` produces a mobile plain-text answer (no Markdown, no rich tables).
    """
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        return {"reply": "The AI assistant isn't configured yet (OPENAI_API_KEY is not set).",
                "tool_calls": [], "error": "no_openai_key",
                "platform": platform, "version": BOT_VERSION}

    start = time.monotonic()
    result = _run_loop(message, history, settings, platform)
    result["latency_ms"] = int((time.monotonic() - start) * 1000)
    result["platform"] = platform
    result["version"] = BOT_VERSION
    _write_audit(message, result, settings)
    return result


def _run_loop(message: str, history: list[dict] | None, settings,
              platform: str = "web") -> dict:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
    )

    # Kept as separate parts so the context safety net can trim history and shrink
    # this run's tool results independently, without touching system/question.
    system_msg = {"role": "system", "content": _system_prompt(platform)}
    hist_msgs = _history_messages(history)            # role+content only — no UI payloads
    current_msg = {"role": "user", "content": message}
    run_msgs: list[dict] = []                         # this run's assistant tool_calls + tool results

    trace: list[dict] = []
    last_candidates: list[list] = []   # ALL row-lists from the most recent data tool
    presentation = None    # the single table the model chose to show (present_table)
    download = None        # a file export the model created (export_table) -> {url, filename, ...}
    tokens_in = tokens_out = 0
    model_used = settings.OPENAI_MODEL
    max_steps = settings.ASSISTANT_MAX_STEPS

    for step in range(max_steps):
        try:
            resp, model_used = _create_fitted(
                client, settings, system_msg, hist_msgs, current_msg, run_msgs)
        except _ContextTooLarge:
            logger.warning("assistant: request too large even for the fallback model")
            return {"reply": _TOO_MUCH_DATA_REPLY, "tool_calls": trace,
                    "datasets": [presentation] if presentation else [],
                    "steps": step + 1, "error": "context_capacity", "model": model_used,
                    "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out}}
        except Exception as exc:  # network / auth / model errors
            logger.exception("OpenAI call failed")
            return {"reply": _GENERIC_ERROR_REPLY, "tool_calls": trace,
                    "error": "openai_error", "model": model_used,
                    "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out}}

        if resp.usage:
            tokens_in += resp.usage.prompt_tokens or 0
            tokens_out += resp.usage.completion_tokens or 0

        msg = resp.choices[0].message
        assistant_msg: dict = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        run_msgs.append(assistant_msg)

        # No tool calls -> final answer.
        if not msg.tool_calls:
            return {
                "reply": msg.content or "",
                "tool_calls": trace,
                "datasets": [presentation] if presentation else [],
                "download": download,
                "steps": step + 1, "model": model_used,
                "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out},
                "prompt": {"name": PROMPT_NAME, "version": PROMPT_VERSION},
            }

        # Otherwise run each requested tool and feed results back.
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            # present_table is a display directive, not a data call — render the
            # last dataset the way the model asked and ack it.
            if tc.function.name == "present_table":
                # Render the candidate list that best matches the columns the model
                # asked for, and — among equal matches — the one it's ranking by.
                rows = _select_dataset(last_candidates, args.get("columns"),
                                       args.get("sort_by"), args.get("sort_desc", True))
                presentation = _apply_presentation(args, rows)
                trace.append({"tool": "present_table", "args": args, "ok": bool(presentation)})
                shown = len(presentation["rows"]) if presentation else 0
                total = presentation["total_available"] if presentation else 0
                run_msgs.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": tool_result_to_message(
                        {"ok": bool(presentation), "shown_rows": shown, "total_rows": total,
                         "note": "table shown to the user" if presentation else "no data to show yet"}),
                })
                continue

            # export_table is a directive too — turn the table just shown into a
            # downloadable .xlsx/.csv and hand back a link (LINE can't attach files).
            if tc.function.name == "export_table":
                if presentation and presentation.get("rows"):
                    from app.assistant import exports
                    download = exports.create_export(
                        presentation.get("title"), presentation.get("columns"),
                        presentation.get("rows"), args.get("format") or "xlsx")
                trace.append({"tool": "export_table", "args": args, "ok": bool(download)})
                ack = ({"ok": True, "format": download["format"],
                        "note": "file created; the download link has been delivered to the user"}
                       if download else
                       {"ok": False, "note": "no table has been shown yet — call present_table first, then export"})
                run_msgs.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": tool_result_to_message(ack)})
                continue

            result = run_tool(tc.function.name, args)
            trace.append({
                "tool": tc.function.name,
                "args": args,
                "ok": result.get("ok", True),
                "error": result.get("error"),
            })
            cands = _extract_datasets(result)  # all row-lists (<=500 each) kept for the UI
            if cands:
                last_candidates = cands
            run_msgs.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": tool_result_to_message(_truncate_for_model(result)),  # capped for the model
            })

    return {
        "reply": "I couldn't finish that within the step limit — try a narrower question.",
        "tool_calls": trace,
        "datasets": [presentation] if presentation else [],
        "download": download,
        "steps": max_steps, "model": model_used,
        "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out},
        "error": "step_limit",
    }


def _write_audit(question: str, result: dict, settings) -> None:
    """Record this turn in a Mongo ``ai_request`` collection. Never fatal."""
    try:
        from app.utils import mongo_store as ms
        db = ms.get_db()
        if db is None:
            return
        usage = result.get("usage") or {}
        db["ai_request"].insert_one({
            "question": question,
            "reply": result.get("reply"),
            "platform": result.get("platform", "web"),
            "bot_version": result.get("version", BOT_VERSION),
            "tool_calls": result.get("tool_calls") or [],
            "steps": result.get("steps"),
            "prompt_name": PROMPT_NAME,
            "prompt_version": PROMPT_VERSION,
            "model": result.get("model") or settings.OPENAI_MODEL,
            "tokens_in": usage.get("tokens_in", 0),
            "tokens_out": usage.get("tokens_out", 0),
            "latency_ms": result.get("latency_ms", 0),
            "state": "error" if result.get("error") else "done",
            "error": result.get("error"),
        })
    except Exception:
        logger.exception("assistant audit write failed (non-fatal)")
