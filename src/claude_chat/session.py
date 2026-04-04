"""Session cache management for claude-chat.

Persists claude_id and passphrase locally so users don't have to re-enter
credentials every launch. The session file lives at ~/.claude/chat/session.json.

Security: The passphrase is encrypted with a device-bound key before storage.
An attacker needs both the session file AND the device key to recover the
passphrase. Sessions expire after SESSION_EXPIRY_DAYS (default 7).
"""

import base64
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nacl.secret import SecretBox
from nacl.utils import random as nacl_random

from claude_chat.config import CHAT_DIR, SESSION_EXPIRY_DAYS, SESSION_FILE, ensure_chat_dir


DEVICE_KEY_FILE = CHAT_DIR / ".device_key"


@dataclass
class Session:
    claude_id: str
    passphrase: str
    user_id: str | None = None  # Supabase auth user id, set after login


def _get_or_create_device_key() -> bytes:
    """Get or create a device-bound encryption key.

    This key is stored separately from the session file.
    An attacker needs BOTH files to recover the passphrase.
    """
    ensure_chat_dir()
    if DEVICE_KEY_FILE.is_file():
        key = DEVICE_KEY_FILE.read_bytes()
        if len(key) == 32:
            return key
    # Generate new device key
    key = nacl_random(32)
    DEVICE_KEY_FILE.write_bytes(key)
    try:
        DEVICE_KEY_FILE.chmod(0o600)
    except OSError:
        pass
    return key


def _encrypt_passphrase(passphrase: str) -> str:
    """Encrypt passphrase with device key. Returns base64-encoded ciphertext."""
    key = _get_or_create_device_key()
    box = SecretBox(key)
    encrypted = box.encrypt(passphrase.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def _decrypt_passphrase(encrypted: str) -> str:
    """Decrypt passphrase with device key. Returns plaintext passphrase."""
    key = _get_or_create_device_key()
    box = SecretBox(key)
    encrypted_bytes = base64.b64decode(encrypted)
    return box.decrypt(encrypted_bytes).decode("utf-8")


def save_session(session: Session) -> None:
    """Save session to ~/.claude/chat/session.json.

    The passphrase is encrypted with a device-bound key before storage.
    Sets file permissions to owner-only (600) on Unix systems.
    On Windows, relies on user directory permissions.
    """
    ensure_chat_dir()
    data = {
        "claude_id": session.claude_id,
        "passphrase_encrypted": _encrypt_passphrase(session.passphrase),
        "user_id": session.user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = SESSION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(SESSION_FILE))
    # Set file permissions on Unix
    try:
        SESSION_FILE.chmod(0o600)
    except OSError:
        pass


def load_session() -> Session | None:
    """Load session from disk. Returns None if no session exists, file is
    corrupted, or the session has expired."""
    if not SESSION_FILE.is_file():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))

        # Check session expiry
        created_str = data.get("created_at")
        if created_str:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - created > timedelta(days=SESSION_EXPIRY_DAYS):
                clear_session()
                return None

        # Support both old (plaintext) and new (encrypted) format for migration
        if "passphrase_encrypted" in data:
            passphrase = _decrypt_passphrase(data["passphrase_encrypted"])
        elif "passphrase" in data:
            # Legacy plaintext format - migrate on next save
            passphrase = data["passphrase"]
        else:
            return None

        return Session(
            claude_id=data["claude_id"],
            passphrase=passphrase,
            user_id=data.get("user_id"),
        )
    except (json.JSONDecodeError, KeyError, TypeError, Exception):
        return None


def clear_session() -> None:
    """Delete the session file (logout)."""
    if SESSION_FILE.is_file():
        SESSION_FILE.unlink()


def has_session() -> bool:
    """Check if a valid session file exists."""
    return load_session() is not None
