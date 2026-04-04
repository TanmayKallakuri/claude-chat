from pathlib import Path

# Local storage
CHAT_DIR = Path.home() / ".claude" / "chat"
SESSION_FILE = CHAT_DIR / "session.json"

# Supabase (anon key is publishable — RLS protects data)
SUPABASE_URL = "https://mesdgreuqahudqxjhgkt.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1lc2RncmV1cWFodWRxeGpoZ2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyNzk3MjIsImV4cCI6MjA5MDg1NTcyMn0.cXtHEajae-Xj7icMdqMWnhQW6-rdxXyZKE5BmStT2Q0"

# Constraints
MAX_REQUESTS_PER_DAY = 3
MAX_CLAUDE_ID_LENGTH = 20
MIN_CLAUDE_ID_LENGTH = 3
MIN_PASSPHRASE_LENGTH = 8

# KDF version (for future migration)
CURRENT_KDF_VERSION = 1

# Session expiry
SESSION_EXPIRY_DAYS = 7


def ensure_chat_dir() -> Path:
    """Create ~/.claude/chat/ if it doesn't exist. Return the path."""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR
