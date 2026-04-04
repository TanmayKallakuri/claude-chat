"""Tests for claude_chat.session module."""

import json

import pytest

from claude_chat.session import (
    Session,
    clear_session,
    has_session,
    load_session,
    save_session,
)


@pytest.fixture(autouse=True)
def _isolate_session(tmp_path, monkeypatch):
    """Redirect SESSION_FILE to a temp directory so tests never touch real config."""
    session_file = tmp_path / "session.json"
    monkeypatch.setattr("claude_chat.session.SESSION_FILE", session_file)
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
    """save_session creates JSON with exactly the expected keys."""
    save_session(Session(claude_id="tk", passphrase="pw", user_id="uid"))
    session_file = tmp_path / "session.json"
    assert session_file.exists()
    data = json.loads(session_file.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"claude_id", "passphrase", "user_id"}
    assert data["claude_id"] == "tk"
    assert data["passphrase"] == "pw"
    assert data["user_id"] == "uid"
