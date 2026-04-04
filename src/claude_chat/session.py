"""Session cache management for claude-chat.

Persists claude_id and passphrase locally so users don't have to re-enter
credentials every launch. The session file lives at ~/.claude/chat/session.json.

Security note: The passphrase is stored in plaintext because we need the raw
value to derive encryption keys each session. File permissions (chmod 600)
mitigate the risk on Unix systems. On Windows, we rely on user-directory ACLs.
"""

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from claude_chat.config import SESSION_FILE, ensure_chat_dir


@dataclass
class Session:
    claude_id: str
    passphrase: str
    user_id: str | None = None  # Supabase auth user id, set after login


def save_session(session: Session) -> None:
    """Save session to ~/.claude/chat/session.json.

    Sets file permissions to owner-only (600) on Unix systems.
    On Windows, relies on user directory permissions.
    """
    ensure_chat_dir()
    data = {
        "claude_id": session.claude_id,
        "passphrase": session.passphrase,
        "user_id": session.user_id,
    }
    SESSION_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Restrict permissions on Unix (no-op concept on Windows)
    if os.name != "nt":
        SESSION_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600


def load_session() -> Session | None:
    """Load session from disk. Returns None if no session exists or file is corrupted."""
    if not SESSION_FILE.is_file():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
        return Session(
            claude_id=data["claude_id"],
            passphrase=data["passphrase"],
            user_id=data.get("user_id"),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def clear_session() -> None:
    """Delete the session file (logout)."""
    if SESSION_FILE.is_file():
        SESSION_FILE.unlink()


def has_session() -> bool:
    """Check if a valid session file exists."""
    return load_session() is not None
