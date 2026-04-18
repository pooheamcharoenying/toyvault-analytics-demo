# app/core/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Public demo mode ---
    # When true, disables Basic Auth so the API is fully public.
    PUBLIC_MODE: bool = False

    # --- Basic Auth (optional when PUBLIC_MODE=true) ---
    BASIC_AUTH_USERNAME: str = "admin"
    BASIC_AUTH_PASSWORD_HASH: str = ""  # bcrypt hash; empty allowed when PUBLIC_MODE=true

    # --- Excel data source (choose one path) ---
    # Option A: HTTP(S) URL to download the Excel on startup (e.g. GitHub Release asset).
    #           Backend downloads, caches to disk, then parses.
    EXCEL_SOURCE_URL: str = ""

    # Option B: DigitalOcean Spaces (legacy path, used if EXCEL_SOURCE_URL is empty)
    DO_ACCESS_KEY: str = ""
    DO_SECRET_KEY: str = ""
    DO_SPACE_NAME: str = "nichiworld"
    DO_REGION: str = "sgp1"

    # --- CORS ---
    # Comma-separated list of allowed origins (e.g. "https://myapp.up.railway.app,http://localhost:3000")
    # Use "*" to allow any origin (only in public demo mode).
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3457"

    # (optional) other global app knobs can live here too
    UPLOAD_DIR: str = "uploads"

    # Pydantic v2 style config
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    # cached singleton; safe to import anywhere
    return Settings()
