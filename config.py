"""
config.py — central bootstrap for hr_mcp_openai (OpenAI-agent variant).

Import FIRST in server.py, the agent, and every adapter so that:
  1. Environment variables (DB creds + OPENAI_API_KEY) load before anything uses them.
  2. A single shared SQLAlchemy engine is created once and reused everywhere.
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

ROOT = Path(__file__).parent.resolve()
load_dotenv(ROOT / ".env")

# ── Database ──────────────────────────────────────────────────────────────────
DB_HOST     = os.environ["DB_HOST"]
DB_USER     = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_NAME     = os.environ.get("DB_NAME", "hr_db")
DB_PORT     = os.environ.get("DB_PORT", "3306")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.environ.get("OPENAI_MODEL", "gpt-4o")

# ── Shared database engine (singleton) ────────────────────────────────────────
from sqlalchemy import create_engine

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True,
    pool_recycle=3600,
)
