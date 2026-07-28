import logging
import os
import secrets
import time
import traceback

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from passlib.context import CryptContext

from app.utils import helper_functions as hf  # <-- use the helper module
from app.core.config import get_settings
from app.utils import digital_ocean_functions as dof
from app.utils import data_client

from app.api.routes.admin_tasks import router as admin_tasks_router
from app.api.routes.file_handling import router as file_handling_router
from app.api.routes.data_analysis import router as data_analysis_router
from app.api.routes.auth import router as auth_router

logger = logging.getLogger(__name__)

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBasic(auto_error=False)

# PUBLIC_MODE bypasses Basic Auth for public demo deployments.
# Set PUBLIC_MODE=true (any truthy) in env to disable auth.
PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "").lower() in ("1", "true", "yes", "on")

# ---------- Auth dependency ----------
def require_basic_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    # Public demo mode — no auth required
    if PUBLIC_MODE:
        return "public"
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Basic"},
        )
    if not secrets.compare_digest(credentials.username, settings.BASIC_AUTH_USERNAME):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    if not pwd_context.verify(credentials.password, settings.BASIC_AUTH_PASSWORD_HASH):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ---------- Response-time + Cache-Control middleware ----------
# Endpoints that must always be fresh (no caching)
_NO_CACHE_PATHS = {"/api/data/status", "/api/data/file_date", "/api/get_data_status"}

class ResponseTimeCacheMiddleware(BaseHTTPMiddleware):
    """Add X-Response-Time header, log slow requests, set Cache-Control."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Response-Time"] = f"{elapsed_ms:.0f}ms"

        path = request.url.path
        if request.method == "GET" and path.startswith("/api/"):
            if path in _NO_CACHE_PATHS:
                response.headers["Cache-Control"] = "no-store"
            else:
                response.headers["Cache-Control"] = "private, max-age=60"

        if elapsed_ms > 500:
            logger.warning("Slow endpoint: %s %s took %.0fms", request.method, path, elapsed_ms)

        return response


# ---------- App & router (protect all routes) ----------
app = FastAPI(title="ToyVault Railway App Backend")


# ---------- Global exception handler ----------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled exceptions and return clean JSON instead of raw tracebacks."""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method,
        request.url.path,
        exc,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )

# Allow origins from env var ALLOWED_ORIGINS (comma-separated)
# Defaults to http://localhost:3000 for local dev
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,                 # needed if you’ll ever use cookies; OK to keep
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],  # crucial so preflight okays your Basic auth header
    expose_headers=["*", "X-Response-Time"],
)
app.add_middleware(ResponseTimeCacheMiddleware)

# Mount the new /api/route test endpoint (same Basic Auth)
app.include_router(admin_tasks_router, prefix="/api", dependencies=[Depends(require_basic_auth)])
app.include_router(file_handling_router, prefix="/api", dependencies=[Depends(require_basic_auth)])
app.include_router(data_analysis_router, prefix="/api", dependencies=[Depends(require_basic_auth)])
# Per-user auth endpoints. Behind the same service Basic auth (the BFF sends it);
# the per-user session check happens inside each route via the X-Session-Token header.
app.include_router(auth_router, prefix="/api", dependencies=[Depends(require_basic_auth)])

# ---------- Public health endpoint ----------
@app.get("/")
async def read_root():
    return {"message": "OK"}




os.makedirs(hf.UPLOAD_DIR, exist_ok=True)


# ----------------------------
# Load newest Excel from DigitalOcean Spaces on startup (background)
# ----------------------------
@app.on_event("startup")
def load_latest_on_startup():
    """
    Three-path startup, in priority order:
    1. DATA_SERVER_URL (local dev, 2-server architecture) - fetch pre-parsed frames
    2. EXCEL_SOURCE_URL (production/demo) - download Excel from a public HTTP URL
    3. DigitalOcean Spaces (legacy production) - requires DO_* credentials
    """
    # Path 1: Data Server (local dev)
    if data_client.DATA_SERVER_URL:
        import threading
        def _load_from_data_server():
            success = data_client.load_from_data_server()
            if not success:
                logger.warning("Data Server failed, trying other sources...")
                _load_fallback()
        threading.Thread(target=_load_from_data_server, daemon=True).start()
        return

    # No data server - use Path 2 or 3 in a background thread so startup doesn't block
    import threading
    threading.Thread(target=_load_fallback, daemon=True).start()


def _load_fallback():
    """Try EXCEL_SOURCE_URL first, then DigitalOcean Spaces."""
    excel_url = getattr(settings, "EXCEL_SOURCE_URL", "")
    if excel_url:
        _load_from_url(excel_url)
        return
    if settings.DO_ACCESS_KEY and settings.DO_SECRET_KEY:
        _load_from_spaces()
        return
    hf._set_status(state="idle", filename=None,
                   error="No data source configured. Set EXCEL_SOURCE_URL or DO_* credentials.")


def _load_from_url(url: str):
    """Download Excel from a public URL (e.g. GitHub Release), cache to disk, parse."""
    import requests
    from pathlib import Path
    import urllib.parse

    # Derive a filename from the URL
    filename = urllib.parse.unquote(url.rsplit("/", 1)[-1].split("?")[0])
    if not filename.lower().endswith(".xlsx"):
        filename = "data.xlsx"

    cache_dir = Path(os.environ.get("EXCEL_CACHE_DIR", ".excel_cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_path = cache_dir / filename

    hf._set_status(state="loading", filename=filename, error=None)
    try:
        # Cache-on-disk strategy: if file already present, skip download
        if not local_path.exists() or local_path.stat().st_size < 1024:
            logger.info("Downloading Excel from %s ...", url)
            with requests.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            logger.info("Downloaded to %s (%d bytes)", local_path, local_path.stat().st_size)
        else:
            logger.info("Using cached Excel: %s", local_path)

        body = local_path.read_bytes()
        dfs = dof._parse_excel_bytes(body)
        with hf.GLOBAL_DF_LOCK:
            hf.GLOBAL_DF = {
                "filename": filename,
                "filedate": hf.extract_date_from_filename(filename),
                **dfs,
            }
        hf._set_status(state="ready", error=None)
        logger.info("Excel loaded from URL. Rows: sale=%d, master=%d, onhand=%d",
                    len(dfs["sale"]), len(dfs["master"]), len(dfs["onhand"]))
    except Exception as e:
        logger.exception("Failed to load Excel from URL")
        hf._set_status(state="error", error=f"URL load failed: {e}")


def _load_from_spaces():
    """Legacy path: load from DigitalOcean Spaces."""
    latest_key = dof.find_latest_excel_key(
        space_name=settings.DO_SPACE_NAME,
        region=settings.DO_REGION,
        access_key=settings.DO_ACCESS_KEY,
        secret_key=settings.DO_SECRET_KEY,
        prefix=getattr(settings, "DO_PREFIX", ""),
    )

    if latest_key is None:
        hf._set_status(state="idle", filename=None, error="No Excel found in Spaces")
        return

    hf.schedule_load_from_spaces_key(
        space_name=settings.DO_SPACE_NAME,
        region=settings.DO_REGION,
        access_key=settings.DO_ACCESS_KEY,
        secret_key=settings.DO_SECRET_KEY,
        key=latest_key,
        background_tasks=None,
    )
