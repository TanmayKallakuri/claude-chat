"""Tests for claude_chat.supabase_client — ChatClient with mocked Supabase."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from nacl.public import PrivateKey

from claude_chat.crypto import (
    derive_keypair,
    encrypt_message,
    get_public_key_bytes,
    public_key_from_bytes,
)
from claude_chat.supabase_client import ChatClient, _bytes_to_db, _bytes_from_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALICE_ID = "alice"
ALICE_PASS = "super-secret-passphrase"
ALICE_UUID = "aaaa-1111-2222-3333"

BOB_ID = "bob"
BOB_PASS = "bob-secret-passphrase"
BOB_UUID = "bbbb-1111-2222-3333"


def _alice_keypair():
    priv = derive_keypair(ALICE_PASS, ALICE_ID)
    return priv, get_public_key_bytes(priv)


def _bob_keypair():
    priv = derive_keypair(BOB_PASS, BOB_ID)
    return priv, get_public_key_bytes(priv)


@dataclass
class FakeAuthUser:
    id: str


@dataclass
class FakeAuthResponse:
    user: FakeAuthUser | None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Create a ChatClient with a fully mocked Supabase client."""
    with patch("claude_chat.supabase_client.create_client") as mock_create:
        mock_sb = MagicMock()
        mock_create.return_value = mock_sb
        c = ChatClient()
        # Expose the mock for assertions
        c._mock_sb = mock_sb
        yield c


def _setup_logged_in(client: ChatClient, claude_id=ALICE_ID, passphrase=ALICE_PASS, user_id=ALICE_UUID):
    """Set client state as if login succeeded."""
    client._user_id = user_id
    client._claude_id = claude_id
    client._private_key = derive_keypair(passphrase, claude_id)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_creates_auth_user_and_inserts_profile(self, client):
        mock_sb = client._mock_sb
        alice_priv, alice_pub = _alice_keypair()

        # Mock auth.sign_up
        mock_sb.auth.sign_up.return_value = FakeAuthResponse(
            user=FakeAuthUser(id=ALICE_UUID)
        )

        # Mock table insert chain
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[{"id": ALICE_UUID}])
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_sb.table.return_value = mock_table

        user_id = client.register(ALICE_ID, ALICE_PASS)

        assert user_id == ALICE_UUID
        assert client._user_id == ALICE_UUID
        assert client._claude_id == ALICE_ID
        assert client._private_key is not None

        # Verify auth.sign_up was called correctly
        mock_sb.auth.sign_up.assert_called_once_with(
            {"email": f"{ALICE_ID}@claudechat.app", "password": ALICE_PASS}
        )

        # Verify users table insert was called
        mock_sb.table.assert_called_with("users")
        insert_args = mock_table.insert.call_args[0][0]
        assert insert_args["id"] == ALICE_UUID
        assert insert_args["claude_id"] == ALICE_ID
        assert insert_args["public_key"] == _bytes_to_db(alice_pub)

    def test_register_raises_on_duplicate_claude_id(self, client):
        mock_sb = client._mock_sb
        mock_sb.auth.sign_up.return_value = FakeAuthResponse(user=None)

        with pytest.raises(ValueError, match="already be taken"):
            client.register(ALICE_ID, ALICE_PASS)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_sets_user_id_and_private_key(self, client):
        mock_sb = client._mock_sb
        mock_sb.auth.sign_in_with_password.return_value = FakeAuthResponse(
            user=FakeAuthUser(id=ALICE_UUID)
        )

        user_id = client.login(ALICE_ID, ALICE_PASS)

        assert user_id == ALICE_UUID
        assert client._user_id == ALICE_UUID
        assert client._claude_id == ALICE_ID
        assert isinstance(client._private_key, PrivateKey)

        mock_sb.auth.sign_in_with_password.assert_called_once_with(
            {"email": f"{ALICE_ID}@claudechat.app", "password": ALICE_PASS}
        )

    def test_login_raises_on_bad_credentials(self, client):
        mock_sb = client._mock_sb
        mock_sb.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")

        with pytest.raises(ValueError, match="Invalid claude_id or passphrase"):
            client.login(ALICE_ID, "wrong-password")


# ---------------------------------------------------------------------------
# Send message (encryption)
# ---------------------------------------------------------------------------

class TestSendMessage:
    def test_send_message_encrypts_before_storing(self, client):
        _setup_logged_in(client)
        mock_sb = client._mock_sb
        bob_priv, bob_pub = _bob_keypair()

        # Cache Bob's public key so it doesn't fetch
        client._public_key_cache[BOB_UUID] = public_key_from_bytes(bob_pub)

        # Mock the insert chain
        mock_insert = MagicMock()
        mock_insert.execute.return_value = MagicMock(data=[{
            "id": "msg-001",
            "sender_id": ALICE_UUID,
            "receiver_id": BOB_UUID,
            "encrypted_content": _bytes_to_db(b"\x00" * 32),
            "nonce": _bytes_to_db(b"\x00" * 24),
            "is_read": False,
            "created_at": "2026-04-03T12:00:00+00:00",
        }])
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_sb.table.return_value = mock_table

        msg = client.send_message(BOB_UUID, "hello bob")

        # Verify it called table("messages").insert(...)
        mock_sb.table.assert_called_with("messages")
        insert_args = mock_table.insert.call_args[0][0]

        # The stored content should be encrypted (hex-encoded), not plaintext
        assert insert_args["encrypted_content"] != "hello bob"
        assert insert_args["encrypted_content"].startswith("\\x")
        assert insert_args["nonce"].startswith("\\x")
        assert insert_args["sender_id"] == ALICE_UUID
        assert insert_args["receiver_id"] == BOB_UUID

        # The returned message should have the plaintext set
        assert msg.plaintext == "hello bob"


# ---------------------------------------------------------------------------
# Get messages (decryption)
# ---------------------------------------------------------------------------

class TestGetMessages:
    def test_get_messages_decrypts_correctly(self, client):
        _setup_logged_in(client)
        mock_sb = client._mock_sb
        bob_priv, bob_pub = _bob_keypair()
        alice_priv, alice_pub = _alice_keypair()

        # Cache Bob's public key
        client._public_key_cache[BOB_UUID] = public_key_from_bytes(bob_pub)

        # Create a real encrypted message (Bob -> Alice)
        bob_private = derive_keypair(BOB_PASS, BOB_ID)
        alice_public = public_key_from_bytes(alice_pub)
        ciphertext, nonce = encrypt_message(bob_private, alice_public, "hey alice!")

        # Mock the query chain
        mock_query = MagicMock()
        mock_query.or_.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=[{
            "id": "msg-002",
            "sender_id": BOB_UUID,
            "receiver_id": ALICE_UUID,
            "encrypted_content": _bytes_to_db(ciphertext),
            "nonce": _bytes_to_db(nonce),
            "is_read": False,
            "created_at": "2026-04-03T12:00:00+00:00",
        }])
        mock_table = MagicMock()
        mock_table.select.return_value = mock_query
        mock_sb.table.return_value = mock_table

        messages = client.get_messages(BOB_UUID, limit=50)

        assert len(messages) == 1
        assert messages[0].plaintext == "hey alice!"
        assert messages[0].sender_id == BOB_UUID


# ---------------------------------------------------------------------------
# Send request (rate limit handling)
# ---------------------------------------------------------------------------

class TestSendRequest:
    def test_send_request_rate_limit_error(self, client):
        _setup_logged_in(client)
        mock_sb = client._mock_sb

        # Mock insert to raise a rate-limit-like error
        mock_insert = MagicMock()
        mock_insert.execute.side_effect = Exception("rate limit exceeded: max 3 requests per 24h")
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_sb.table.return_value = mock_table

        with pytest.raises(ValueError, match="Rate limit exceeded"):
            client.send_request("some-user-id")

    def test_send_request_duplicate_error(self, client):
        _setup_logged_in(client)
        mock_sb = client._mock_sb

        mock_insert = MagicMock()
        mock_insert.execute.side_effect = Exception("unique constraint violated")
        mock_table = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_sb.table.return_value = mock_table

        with pytest.raises(ValueError, match="already exists"):
            client.send_request("some-user-id")


# ---------------------------------------------------------------------------
# Respond to request
# ---------------------------------------------------------------------------

class TestRespondToRequest:
    def test_accept_request_updates_status(self, client):
        _setup_logged_in(client)
        mock_sb = client._mock_sb

        mock_update = MagicMock()
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock(data=[])
        mock_table = MagicMock()
        mock_table.update.return_value = mock_update
        mock_sb.table.return_value = mock_table

        client.respond_to_request("req-001", accept=True)

        mock_sb.table.assert_called_with("requests")
        mock_table.update.assert_called_once_with({"status": "accepted"})

    def test_reject_request_updates_status(self, client):
        _setup_logged_in(client)
        mock_sb = client._mock_sb

        mock_update = MagicMock()
        mock_update.eq.return_value = mock_update
        mock_update.execute.return_value = MagicMock(data=[])
        mock_table = MagicMock()
        mock_table.update.return_value = mock_update
        mock_sb.table.return_value = mock_table

        client.respond_to_request("req-001", accept=False)

        mock_table.update.assert_called_once_with({"status": "rejected"})


# ---------------------------------------------------------------------------
# Bytes conversion helpers
# ---------------------------------------------------------------------------

class TestBytesConversion:
    def test_bytes_round_trip(self):
        original = b"\xde\xad\xbe\xef"
        db_value = _bytes_to_db(original)
        assert db_value == "\\xdeadbeef"
        assert _bytes_from_db(db_value) == original

    def test_bytes_from_db_raw_bytes(self):
        assert _bytes_from_db(b"\xab\xcd") == b"\xab\xcd"

    def test_bytes_from_db_double_backslash(self):
        assert _bytes_from_db("\\\\xdeadbeef") == b"\xde\xad\xbe\xef"

    def test_bytes_from_db_plain_hex(self):
        assert _bytes_from_db("deadbeef") == b"\xde\xad\xbe\xef"


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_search_users_requires_auth(self, client):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            client.search_users("alice")

    def test_send_message_requires_auth(self, client):
        with pytest.raises(RuntimeError, match="Not authenticated"):
            client.send_message("some-id", "hello")
