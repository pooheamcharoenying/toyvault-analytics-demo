"""Public file-download route for AI-assist exports.

PUBLIC (no Basic auth) so a LINE user can tap the download link on their phone
without credentials. Security is the unguessable token + 1-hour TTL — see
``app.assistant.exports``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.assistant import exports

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])


@router.get("/export/{token}", summary="Download an AI-assist export (public, tokenized)")
def download_export(token: str):
    rec = exports.get_export(token)
    if not rec:
        raise HTTPException(status_code=404,
                            detail="This download link has expired or is invalid.")
    return Response(
        content=rec["data"],
        media_type=rec["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{rec["filename"]}"'},
    )
