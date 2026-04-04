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

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

# Constraints
MAX_REQUESTS_PER_DAY = 3
MAX_CLAUDE_ID_LENGTH = 20
MIN_CLAUDE_ID_LENGTH = 3
MIN_PASSPHRASE_LENGTH = 8

# KDF version (for future migration)
CURRENT_KDF_VERSION = 1

# Session expiry
SESSION_EXPIRY_DAYS = 7

# Pusher (real-time message delivery)
PUSHER_APP_ID = os.environ.get("PUSHER_APP_ID", "")
PUSHER_KEY = os.environ.get("PUSHER_KEY", "")
PUSHER_SECRET = os.environ.get("PUSHER_SECRET", "")
PUSHER_CLUSTER = os.environ.get("PUSHER_CLUSTER", "")


def ensure_chat_dir() -> Path:
    """Create ~/.claude/chat/ if it doesn't exist. Return the path."""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR
