import base64
from datetime import datetime

import pytest

from claude_chat.models import Connection, ConnectionRequest, Message, User


class TestUser:
    def test_round_trip(self):
        user = User(
            id="u1",
            claude_id="alice",
            public_key=b"\x01\x02\x03",
            kdf_version=1,
            created_at=datetime(2026, 1, 15, 12, 0, 0),
        )
        data = user.to_dict()
        restored = User.from_dict(data)
        assert restored.id == user.id
        assert restored.claude_id == user.claude_id
        assert restored.public_key == user.public_key
        assert restored.kdf_version == user.kdf_version
        assert restored.created_at == user.created_at

    def test_bytes_base64(self):
        key = b"\xde\xad\xbe\xef"
        user = User(id="u1", claude_id="bob", public_key=key)
        data = user.to_dict()
        assert data["public_key"] == base64.b64encode(key).decode("ascii")
        restored = User.from_dict(data)
        assert restored.public_key == key

    def test_datetime_serialization(self):
        dt = datetime(2026, 3, 20, 8, 30, 0)
        user = User(id="u1", claude_id="carol", public_key=b"k", created_at=dt)
        data = user.to_dict()
        assert data["created_at"] == dt.isoformat()
        restored = User.from_dict(data)
        assert restored.created_at == dt

    def test_none_optional_fields(self):
        user = User(id="u1", claude_id="dave", public_key=b"k")
        data = user.to_dict()
        assert data["created_at"] is None
        restored = User.from_dict(data)
        assert restored.created_at is None

    def test_defaults(self):
        user = User(id="u1", claude_id="eve", public_key=b"k")
        assert user.kdf_version == 1
        assert user.created_at is None


class TestConnectionRequest:
    def test_round_trip(self):
        cr = ConnectionRequest(
            id="cr1",
            sender_id="u1",
            receiver_id="u2",
            status="accepted",
            created_at=datetime(2026, 2, 1),
            sender_claude_id="alice",
            receiver_claude_id="bob",
        )
        restored = ConnectionRequest.from_dict(cr.to_dict())
        assert restored.id == cr.id
        assert restored.sender_id == cr.sender_id
        assert restored.receiver_id == cr.receiver_id
        assert restored.status == cr.status
        assert restored.created_at == cr.created_at
        assert restored.sender_claude_id == cr.sender_claude_id
        assert restored.receiver_claude_id == cr.receiver_claude_id

    def test_none_optional_fields(self):
        cr = ConnectionRequest(id="cr1", sender_id="u1", receiver_id="u2")
        data = cr.to_dict()
        assert data["sender_claude_id"] is None
        assert data["receiver_claude_id"] is None
        assert data["created_at"] is None
        restored = ConnectionRequest.from_dict(data)
        assert restored.sender_claude_id is None
        assert restored.receiver_claude_id is None
        assert restored.created_at is None

    def test_defaults(self):
        cr = ConnectionRequest(id="cr1", sender_id="u1", receiver_id="u2")
        assert cr.status == "pending"
        assert cr.created_at is None
        assert cr.sender_claude_id is None
        assert cr.receiver_claude_id is None


class TestConnection:
    def test_round_trip(self):
        conn = Connection(
            id="c1",
            user_a="u1",
            user_b="u2",
            created_at=datetime(2026, 4, 1, 10, 0),
        )
        restored = Connection.from_dict(conn.to_dict())
        assert restored.id == conn.id
        assert restored.user_a == conn.user_a
        assert restored.user_b == conn.user_b
        assert restored.created_at == conn.created_at
        assert restored.other_user is None

    def test_with_other_user(self):
        other = User(id="u2", claude_id="bob", public_key=b"\xab\xcd")
        conn = Connection(id="c1", user_a="u1", user_b="u2", other_user=other)
        data = conn.to_dict()
        assert data["other_user"] is not None
        restored = Connection.from_dict(data)
        assert restored.other_user is not None
        assert restored.other_user.id == "u2"
        assert restored.other_user.claude_id == "bob"
        assert restored.other_user.public_key == b"\xab\xcd"

    def test_none_optional_fields(self):
        conn = Connection(id="c1", user_a="u1", user_b="u2")
        data = conn.to_dict()
        assert data["created_at"] is None
        assert data["other_user"] is None
        restored = Connection.from_dict(data)
        assert restored.created_at is None
        assert restored.other_user is None


class TestMessage:
    def test_round_trip(self):
        msg = Message(
            id="m1",
            sender_id="u1",
            receiver_id="u2",
            encrypted_content=b"\x00\x11\x22\x33",
            nonce=b"\xaa\xbb\xcc",
            is_read=True,
            created_at=datetime(2026, 4, 2, 14, 30),
            plaintext="hello",
            sender_claude_id="alice",
        )
        restored = Message.from_dict(msg.to_dict())
        assert restored.id == msg.id
        assert restored.sender_id == msg.sender_id
        assert restored.receiver_id == msg.receiver_id
        assert restored.encrypted_content == msg.encrypted_content
        assert restored.nonce == msg.nonce
        assert restored.is_read == msg.is_read
        assert restored.created_at == msg.created_at
        assert restored.plaintext == msg.plaintext
        assert restored.sender_claude_id == msg.sender_claude_id

    def test_bytes_base64(self):
        content = b"\xff\xfe\xfd"
        nonce = b"\x01\x02"
        msg = Message(
            id="m1",
            sender_id="u1",
            receiver_id="u2",
            encrypted_content=content,
            nonce=nonce,
        )
        data = msg.to_dict()
        assert data["encrypted_content"] == base64.b64encode(content).decode("ascii")
        assert data["nonce"] == base64.b64encode(nonce).decode("ascii")
        restored = Message.from_dict(data)
        assert restored.encrypted_content == content
        assert restored.nonce == nonce

    def test_datetime_serialization(self):
        dt = datetime(2026, 4, 3, 9, 15, 30)
        msg = Message(
            id="m1",
            sender_id="u1",
            receiver_id="u2",
            encrypted_content=b"x",
            nonce=b"n",
            created_at=dt,
        )
        data = msg.to_dict()
        assert data["created_at"] == dt.isoformat()
        restored = Message.from_dict(data)
        assert restored.created_at == dt

    def test_none_optional_fields(self):
        msg = Message(
            id="m1",
            sender_id="u1",
            receiver_id="u2",
            encrypted_content=b"x",
            nonce=b"n",
        )
        data = msg.to_dict()
        assert data["created_at"] is None
        assert data["plaintext"] is None
        assert data["sender_claude_id"] is None
        restored = Message.from_dict(data)
        assert restored.created_at is None
        assert restored.plaintext is None
        assert restored.sender_claude_id is None

    def test_defaults(self):
        msg = Message(
            id="m1",
            sender_id="u1",
            receiver_id="u2",
            encrypted_content=b"x",
            nonce=b"n",
        )
        assert msg.is_read is False
        assert msg.created_at is None
        assert msg.plaintext is None
        assert msg.sender_claude_id is None
