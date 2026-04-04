"""Tests for claude_chat.session module."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from claude_chat.session import (
    DEVICE_KEY_FILE,
    Session,
    clear_session,
    has_session,
    load_session,
    save_session,
)


@pytest.fixture(autouse=True)
def _isolate_session(tmp_path, monkeypatch):
    """Redirect SESSION_FILE and DEVICE_KEY_FILE to a temp directory so tests
    never touch real config."""
    session_file = tmp_path / "session.json"
    device_key_file = tmp_path / ".device_key"
    monkeypatch.setattr("claude_chat.session.SESSION_FILE", session_file)
    monkeypatch.setattr("claude_chat.session.DEVICE_KEY_FILE", device_key_file)
    monkeypatch.setattr("claude_chat.session.ensure_chat_dir", lambda: tmp_path)


def test_save_and_load_roundtrip(tmp_path):
    """save_session then load_session round-trip works."""
    session = Session(claude_id="tanmay_k", passphrase="supersecret", user_id="uuid-123")
    save_session(session)
    loaded = load_session()

    assert loaded is not None
    assert loaded.claude_id == "tanmay_k"
    assert loaded.passphrase == "supersecret"
    assert loaded.user_id == "uuid-123"


def test_load_returns_none_when_no_file():
    """load_session returns None when no file exists."""
    assert load_session() is None


def test_clear_session_removes_file(tmp_path):
    """clear_session removes the file."""
    save_session(Session(claude_id="x", passphrase="y"))
    session_file = tmp_path / "session.json"
    assert session_file.exists()

    clear_session()
    assert not session_file.exists()


def test_has_session_true_false(tmp_path):
    """has_session returns True/False correctly."""
    assert has_session() is False

    save_session(Session(claude_id="a", passphrase="b"))
    assert has_session() is True

    clear_session()
    assert has_session() is False


def test_corrupted_json_returns_none(tmp_path):
    """Corrupted JSON file returns None from load_session (doesn't crash)."""
    session_file = tmp_path / "session.json"
    session_file.write_text("{invalid json!!", encoding="utf-8")

    assert load_session() is None


def test_session_with_user_id_none(tmp_path):
    """Session with user_id=None serializes correctly."""
    save_session(Session(claude_id="user1", passphrase="pass1"))
    loaded = load_session()

    assert loaded is not None
    assert loaded.user_id is None

    # Verify the JSON on disk has null for user_id
    session_file = tmp_path / "session.json"
    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert data["user_id"] is None


def test_save_creates_file_with_correct_keys(tmp_path):
    """save_session creates JSON with expected keys including encrypted passphrase."""
    save_session(Session(claude_id="tk", passphrase="pw", user_id="uid"))
    session_file = tmp_path / "session.json"
    assert session_file.exists()
    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"claude_id", "passphrase_encrypted", "user_id", "created_at"}
    assert data["claude_id"] == "tk"
    assert data["user_id"] == "uid"


def test_no_plaintext_passphrase_on_disk(tmp_path):
    """Saved session file does NOT contain the plaintext passphrase."""
    save_session(Session(claude_id="tk", passphrase="my_secret_pass"))
    session_file = tmp_path / "session.json"
    raw = session_file.read_text(encoding="utf-8")
    assert "my_secret_pass" not in raw
    # Should have the encrypted key instead
    data = json.loads(raw)
    assert "passphrase" not in data
    assert "passphrase_encrypted" in data


def test_encrypted_passphrase_decrypts_correctly(tmp_path):
    """Encrypted passphrase can be decrypted back to the original value."""
    from claude_chat.session import _decrypt_passphrase, _encrypt_passphrase

    encrypted = _encrypt_passphrase("test_passphrase_123")
    decrypted = _decrypt_passphrase(encrypted)
    assert decrypted == "test_passphrase_123"


def test_backward_compatibility_plaintext_format(tmp_path):
    """Old format with plaintext 'passphrase' key still loads correctly."""
    session_file = tmp_path / "session.json"
    legacy_data = {
        "claude_id": "old_user",
        "passphrase": "old_pass",
        "user_id": "old_uid",
    }
    session_file.write_text(json.dumps(legacy_data), encoding="utf-8")

    loaded = load_session()
    assert loaded is not None
    assert loaded.claude_id == "old_user"
    assert loaded.passphrase == "old_pass"
    assert loaded.user_id == "old_uid"


def test_session_expiry_old_session_returns_none(tmp_path):
    """Session with created_at older than SESSION_EXPIRY_DAYS returns None."""
    from claude_chat.session import _encrypt_passphrase

    session_file = tmp_path / "session.json"
    old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    data = {
        "claude_id": "expired_user",
        "passphrase_encrypted": _encrypt_passphrase("expired_pass"),
        "user_id": None,
        "created_at": old_time,
    }
    session_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_session()
    assert loaded is None
    # Session file should be cleared
    assert not session_file.exists()


def test_session_not_expired_within_window(tmp_path):
    """Session within the expiry window loads successfully."""
    from claude_chat.session import _encrypt_passphrase

    session_file = tmp_path / "session.json"
    recent_time = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    data = {
        "claude_id": "fresh_user",
        "passphrase_encrypted": _encrypt_passphrase("fresh_pass"),
        "user_id": "uid",
        "created_at": recent_time,
    }
    session_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_session()
    assert loaded is not None
    assert loaded.claude_id == "fresh_user"
    assert loaded.passphrase == "fresh_pass"


def test_device_key_file_created(tmp_path):
    """Device key file is created when saving a session."""
    device_key_file = tmp_path / ".device_key"
    assert not device_key_file.exists()

    save_session(Session(claude_id="dk", passphrase="test"))
    assert device_key_file.exists()
    assert len(device_key_file.read_bytes()) == 32
