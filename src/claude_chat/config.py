import os
from pathlib import Path

# Local storage
CHAT_DIR = Path.home() / ".claude" / "chat"
SESSION_FILE = CHAT_DIR / "session.json"
ENV_FILE = CHAT_DIR / ".env"

def _load_env() -> None:
    """Load environment variables from ~/.claude/chat/.env if it exists."""
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

_load_env()

# Supabase (anon key is publishable by design — RLS protects data)
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://mesdgreuqahudqxjhgkt.supabase.co"
)
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lc2RncmV1cWFodWRxeGpoZ2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyNzk3MjIsImV4cCI6MjA5MDg1NTcyMn0.cXtHEajae-Xj7icMdqMWnhQW6-rdxXyZKE5BmStT2Q0",
)

# Constraints
MAX_REQUESTS_PER_DAY = 3
MAX_CLAUDE_ID_LENGTH = 20
MIN_CLAUDE_ID_LENGTH = 3
MIN_PASSPHRASE_LENGTH = 8

# KDF version (for future migration)
CURRENT_KDF_VERSION = 1

# Session expiry
SESSION_EXPIRY_DAYS = 7

# Pusher (key and cluster are publishable client-side values)
PUSHER_APP_ID = os.environ.get("PUSHER_APP_ID", "2136945")
PUSHER_KEY = os.environ.get("PUSHER_KEY", "289abe33362ab3faebd8")
PUSHER_SECRET = os.environ.get("PUSHER_SECRET", "")  # must be set via .env
PUSHER_CLUSTER = os.environ.get("PUSHER_CLUSTER", "us3")


def ensure_chat_dir() -> Path:
    """Create ~/.claude/chat/ if it doesn't exist. Return the path."""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR
