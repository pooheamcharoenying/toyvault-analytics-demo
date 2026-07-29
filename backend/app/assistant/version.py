"""Single source of truth for the AI Assist bot version.

Bump ``BOT_VERSION`` on any change that affects how the bot answers — the system
prompt, the set of tools, or how results are rendered. It is stamped onto every
reply (web and LINE) and persisted with each stored assistant message, so a saved
thread always shows which bot version produced each answer. That traceability
matters now that production chat threads are kept, not deleted.

Keep a one-line note in CHANGES when bumping, so an old answer's version is
meaningful when someone reads it back weeks later.
"""

BOT_VERSION = "1.0.13"

# version -> what changed (newest first). Human-readable, for our own reference.
CHANGES = {
    "1.0.13": "Let the bot DO the math. Prompt rule #1 no longer forbids arithmetic — "
              "it may now derive figures from retrieved numbers (run-rate projections, "
              "growth/YoY/MoM %, shares, sums, averages, per-unit, days of cover) and "
              "must show its working; only the INPUTS must come from tools. Fixes the "
              "bot refusing to project a partial month's sales to a full-month run rate.",
    "1.0.12": "Make the /reset (and /help) acknowledgement reliable: send it via "
              "push instead of the reply token, guard the thread reset, and RETRY "
              "transient LINE push failures (429/5xx) — a one-off 500 was silently "
              "dropping messages. Clearer 'New chat session started' message.",
    "1.0.11": "LINE text commands: '/reset' (also 'reset', 'เริ่มใหม่', …) starts a "
              "fresh conversation — points the binding at a new empty thread so no "
              "prior context leaks; '/help' shows usage. Matched as exact phrases so "
              "normal questions aren't caught.",
    "1.0.10": "Fix silent no-reply on wide tables: a 6-column × 12-row Flex card "
              "exceeded LINE's component limit (400), and because the whole push "
              "failed the user got nothing. Now (1) cap the card by a cols×rows cell "
              "budget so LINE accepts it, and (2) if any rich push is still rejected, "
              "fall back to a plain-text push so there's never total silence.",
    "1.0.9": "Download button now forces the phone's external browser "
             "(openExternalBrowser=1) — LINE's in-app browser blocks file downloads, "
             "so the link was opening but couldn't save the file.",
    "1.0.8": "LINE UX: show the loading ('typing…') animation while the agent works "
             "(LINE Loading Indicator API), and replace the raw download URL with a "
             "tappable '⬇ Download' button (Flex). NB: LINE's bot API has no file "
             "message type, so a file can't be attached in-chat — the link is the way.",
    "1.0.7": "Fix table showing the OPPOSITE of the question when a tool returns "
             "several lists with identical columns (top-sellers vs top-by-on-hand "
             "vs non-movers): present_table now picks, among equal column matches, "
             "the list most extreme on the model's sort_by, so the table matches the "
             "ranking asked for. Prompt: don't inherit a year/filter from earlier "
             "turns; route 'slow-moving / high stock-to-sales' to non_movers/dead_stock.",
    "1.0.6": "LINE tables now render as a Flex Message card (header row, aligned "
             "columns, separators, right-aligned ฿) instead of a plain-text list — "
             "for up to 6 columns / 12 rows; wider/longer tables fall back to plain "
             "text. Plain text is kept as the Flex altText.",
    "1.0.5": "File export: `export_table` turns the table just shown into a "
             "downloadable .xlsx/.csv served behind a tokenized, 1-hour-expiry link "
             "(LINE can't attach files, so the bot sends a link). The model no longer "
             "wrongly claims it can't create a file.",
    "1.0.4": "present_table now renders the tool-result list that MATCHES the "
             "columns the model asked for (most requested fields present), instead "
             "of blindly using the largest list. Fixes tables that silently dropped "
             "requested columns and showed the wrong entity (e.g. asked for item "
             "on-hand qty/value + sold qty/value, but got a brand list with only 2 "
             "columns because top_brands happened to be the largest list).",
    "1.0.3": "Tolerant location matching: location lookups now resolve near-miss "
             "spellings (exact → normalized → fuzzy) so a one-character typo like "
             "'M-Grandway Rivrside' vs the stored 'M-Grandway Riverside' finds the branch instead of "
             "wrongly reporting 'no data'.",
    "1.0.2": "Context-overflow safety net: estimate tokens and TRIM to fit before "
             "every model call (drop oldest history, shrink oldest tool results with "
             "breadcrumbs, pair-safe); if it still won't fit, fall back to a "
             "bigger-context model; if even that won't fit, refuse gracefully with a "
             "narrowing hint. All API errors become friendly messages (no raw 400s).",
    "1.0.1": "Fix context_length_exceeded: cap large tool results fed to the model "
             "(the full list still goes to the UI table/CSV), and strip dataset "
             "payloads from chat history sent back each turn.",
    "1.0.0": "First production release: 35 grounded data tools, per-user threads, "
             "LINE integration, platform-specific answers (web rich tables / LINE "
             "plain-text), guaranteed name column, version stamping.",
}
