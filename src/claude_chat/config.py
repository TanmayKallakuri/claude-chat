from pathlib import Path

# Local storage
CHAT_DIR = Path.home() / ".claude" / "chat"
SESSION_FILE = CHAT_DIR / "session.json"

# Supabase — placeholders for now (will be filled when project is created)
SUPABASE_URL = ""  # TODO: fill after Supabase project creation
SUPABASE_ANON_KEY = ""  # TODO: fill after Supabase project creation

# Constraints
MAX_REQUESTS_PER_DAY = 3
MAX_CLAUDE_ID_LENGTH = 20
MIN_CLAUDE_ID_LENGTH = 3
MIN_PASSPHRASE_LENGTH = 8

# KDF version (for future migration)
CURRENT_KDF_VERSION = 1


def ensure_chat_dir() -> Path:
    """Create ~/.claude/chat/ if it doesn't exist. Return the path."""
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    return CHAT_DIR
