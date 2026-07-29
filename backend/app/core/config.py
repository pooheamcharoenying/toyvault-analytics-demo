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
    DO_SPACE_NAME: str = "toyvault-demo"
    DO_REGION: str = "sgp1"

    # --- MongoDB (app-owned collections only: users, planogram, assistant threads,
    #     LINE bindings). NOT the analytics data source — that stays Excel/Spaces.
    #     Cluster host + DB are baked in below (neither is a secret); at runtime you
    #     only supply the two credentials MONGODB_USER_ME + MONGODB_PASSWORD_ME as env
    #     vars and mongo_store assembles the mongodb+srv URI. (MONGODB_URI still wins
    #     if set, as a full-override escape hatch.) Everything is scoped to MONGODB_DB;
    #     the cluster is shared, so isolation is by database name. Creds never committed. ---
    MONGODB_URI: str = ""
    MONGODB_USER_ME: str = ""
    MONGODB_PASSWORD_ME: str = ""
    MONGODB_HOST: str = "studysabaiapp.fiqyj.mongodb.net"
    MONGODB_DB: str = "toyvaultdemo"

    # --- Per-user auth (login) ---
    # Passwords are bcrypt-hashed in the `users` collection; sessions are signed
    # tokens (HMAC-SHA256). SESSION_SECRET signs those tokens — SET a long random
    # value in production; if empty it falls back to a stable per-deployment secret.
    SESSION_SECRET: str = ""
    SESSION_TTL_HOURS: int = 24

    # --- CORS ---
    # Comma-separated list of allowed origins (e.g. "https://myapp.up.railway.app,http://localhost:3000")
    # Use "*" to allow any origin (only in public demo mode).
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:3457"

    # (optional) other global app knobs can live here too
    UPLOAD_DIR: str = "uploads"

    # --- OpenAI (AI Assist chat agent) ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TIMEOUT_SECONDS: float = 60.0
    OPENAI_MAX_RETRIES: int = 2
    ASSISTANT_MAX_STEPS: int = 12
    OPENAI_CONTEXT_LIMIT: int = 128000
    OPENAI_MODEL_LARGE: str = "gpt-4.1"
    OPENAI_LARGE_CONTEXT_LIMIT: int = 1000000

    # --- Public base URL (used to build tokenized export download links) ---
    PUBLIC_BASE_URL: str = "https://toyvault-analytics-demo-production.up.railway.app"

    # --- LINE Messaging API (AI Assist over LINE) ---
    LINE_CHANNEL_SECRET: str = ""
    LINE_CHANNEL_ACCESS_TOKEN: str = ""

    # Pydantic v2 style config
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    # cached singleton; safe to import anywhere
    return Settings()
