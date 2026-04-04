"""Supabase client for claude-chat.

Handles authentication, user management, friend requests, connections,
and encrypted messaging via Supabase. Real-time delivery uses Pusher.
"""

from __future__ import annotations

from datetime import datetime

from nacl.public import PrivateKey, PublicKey
from supabase import create_client, Client

from claude_chat.config import SUPABASE_URL, SUPABASE_ANON_KEY, CURRENT_KDF_VERSION
from claude_chat.crypto import (
    derive_keypair,
    get_public_key_bytes,
    public_key_from_bytes,
    encrypt_message,
    decrypt_message,
    encrypt_message_ephemeral,
    decrypt_message_ephemeral,
    generate_safety_number,
)
from claude_chat.models import User, Message, ConnectionRequest


def _bytes_from_db(value) -> bytes:
    """Convert a BYTEA value from Supabase (hex string with \\x prefix) to bytes."""
    if value is None:
        raise ValueError("DB returned null for a required bytes field")
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        # Check longer prefix first to avoid shadowing
        if value.startswith("\\\\x"):
            return bytes.fromhex(value[3:])
        if value.startswith("\\x"):
            return bytes.fromhex(value[2:])
        # Try plain hex
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass
    raise ValueError(f"Cannot convert DB value to bytes: {value!r}")


def _bytes_to_db(data: bytes) -> str:
    """Convert bytes to a hex string for BYTEA storage: \\x prefix."""
    return "\\x" + data.hex()


def _parse_user_row(row: dict) -> User:
    """Parse a users table row into a User model."""
    return User(
        id=row["id"],
        claude_id=row["claude_id"],
        public_key=_bytes_from_db(row["public_key"]),
        kdf_version=row.get("kdf_version", 1),
        created_at=_parse_dt(row.get("created_at")),
    )


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _parse_message_row(row: dict) -> Message:
    """Parse a messages table row into a Message (without decryption)."""
    epk_raw = row.get("ephemeral_public_key")
    ephemeral_public_key = _bytes_from_db(epk_raw) if epk_raw is not None else None
    return Message(
        id=row["id"],
        sender_id=row["sender_id"],
        receiver_id=row["receiver_id"],
        encrypted_content=_bytes_from_db(row["encrypted_content"]),
        nonce=_bytes_from_db(row["nonce"]),
        is_read=row.get("is_read", False),
        created_at=_parse_dt(row.get("created_at")),
        ephemeral_public_key=ephemeral_public_key,
    )


def _parse_request_row(row: dict) -> ConnectionRequest:
    """Parse a requests table row into a ConnectionRequest."""
    # Handle joined user data
    sender_claude_id = None
    receiver_claude_id = None
    if isinstance(row.get("sender"), dict):
        sender_claude_id = row["sender"].get("claude_id")
    if isinstance(row.get("receiver"), dict):
        receiver_claude_id = row["receiver"].get("claude_id")

    return ConnectionRequest(
        id=row["id"],
        sender_id=row["sender_id"],
        receiver_id=row["receiver_id"],
        status=row.get("status", "pending"),
        created_at=_parse_dt(row.get("created_at")),
        sender_claude_id=sender_claude_id,
        receiver_claude_id=receiver_claude_id,
    )


class ChatClient:
    """Handles all Supabase interactions for claude-chat."""

    def __init__(self):
        self._supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        self._user_id: str | None = None
        self._claude_id: str | None = None
        self._private_key: PrivateKey | None = None
        self._public_key_cache: dict[str, PublicKey] = {}  # user_id -> PublicKey
        self._realtime = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def register(self, claude_id: str, passphrase: str) -> str:
        """Register a new user. Returns user_id.

        1. Sign up via Supabase Auth
        2. Derive keypair from passphrase + claude_id
        3. INSERT into public.users
        4. Set internal state
        """
        email = f"{claude_id}@claudechat.app"

        try:
            auth_response = self._supabase.auth.sign_up(
                {"email": email, "password": passphrase}
            )
        except Exception as exc:
            msg = str(exc).replace(email, claude_id)
            if "email" in msg.lower():
                msg = "Registration failed: that claude_id may already be taken"
            else:
                msg = f"Registration failed: {msg}"
            raise ValueError(msg) from exc

        user = auth_response.user
        if user is None:
            raise ValueError(
                "Registration failed: that claude_id may already be taken"
            )

        user_id = user.id
        private_key = derive_keypair(passphrase, claude_id)
        pub_bytes = get_public_key_bytes(private_key)

        try:
            self._supabase.table("users").insert(
                {
                    "id": user_id,
                    "claude_id": claude_id,
                    "public_key": _bytes_to_db(pub_bytes),
                    "kdf_version": CURRENT_KDF_VERSION,
                }
            ).execute()
        except Exception as exc:
            # Clean up orphaned auth user
            try:
                self._supabase.auth.sign_out()
            except Exception:
                pass  # Best effort cleanup
            raise ValueError(f"Failed to create user profile: {exc}") from exc

        self._user_id = user_id
        self._claude_id = claude_id
        self._private_key = private_key
        return user_id

    def login(self, claude_id: str, passphrase: str) -> str:
        """Login an existing user. Returns user_id."""
        email = f"{claude_id}@claudechat.app"

        try:
            auth_response = self._supabase.auth.sign_in_with_password(
                {"email": email, "password": passphrase}
            )
        except Exception as exc:
            msg = str(exc).replace(email, claude_id)
            if "email" in msg.lower() or "credentials" in msg.lower():
                msg = "Invalid claude_id or passphrase"
            else:
                msg = f"Login failed: {msg}"
            raise ValueError(msg) from exc

        user = auth_response.user
        if user is None:
            raise ValueError("Login failed: invalid credentials")

        user_id = user.id

        # Verify users row exists
        try:
            user_row = self._supabase.table("users").select("id").eq("id", user_id).execute()
            if not user_row.data:
                raise ValueError("Account incomplete — please register again")
        except Exception as exc:
            if "incomplete" in str(exc):
                raise
            raise ValueError(f"Login failed: {exc}") from exc

        self._user_id = user_id
        self._claude_id = claude_id
        self._private_key = derive_keypair(passphrase, claude_id)
        return user_id

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def search_users(self, query: str) -> list[User]:
        """Search users by claude_id (partial match, case-insensitive).

        Excludes the current user from results.
        """
        self._require_auth()

        response = (
            self._supabase.table("users")
            .select("*")
            .ilike("claude_id", f"%{query}%")
            .neq("id", self._user_id)
            .execute()
        )
        return [_parse_user_row(row) for row in response.data]

    # ------------------------------------------------------------------
    # Friend requests
    # ------------------------------------------------------------------

    def send_request(self, target_user_id: str) -> ConnectionRequest:
        """Send a friend request to another user."""
        self._require_auth()

        try:
            response = (
                self._supabase.table("requests")
                .insert(
                    {
                        "sender_id": self._user_id,
                        "receiver_id": target_user_id,
                        "status": "pending",
                    }
                )
                .execute()
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "unique" in msg or "duplicate" in msg:
                raise ValueError("A request already exists for this user") from exc
            if "rate" in msg or "limit" in msg or "max" in msg:
                raise ValueError(
                    "Rate limit exceeded: max 3 requests per 24 hours"
                ) from exc
            raise ValueError(f"Failed to send request: {exc}") from exc

        row = response.data[0]

        # Notify receiver via Pusher (instant delivery)
        if self._realtime:
            self._realtime.publish_request(
                target_user_id,
                {
                    "sender_id": self._user_id,
                    "sender_claude_id": self._claude_id,
                    "request_id": row["id"],
                },
            )

        return ConnectionRequest(
            id=row["id"],
            sender_id=row["sender_id"],
            receiver_id=row["receiver_id"],
            status=row["status"],
            created_at=_parse_dt(row.get("created_at")),
            sender_claude_id=self._claude_id,
        )

    def get_incoming_requests(self) -> list[ConnectionRequest]:
        """Get pending friend requests received by the current user."""
        self._require_auth()

        response = (
            self._supabase.table("requests")
            .select("*, sender:sender_id(claude_id)")
            .eq("receiver_id", self._user_id)
            .eq("status", "pending")
            .execute()
        )
        return [_parse_request_row(row) for row in response.data]

    def get_outgoing_requests(self) -> list[ConnectionRequest]:
        """Get pending friend requests sent by the current user."""
        self._require_auth()

        response = (
            self._supabase.table("requests")
            .select("*, receiver:receiver_id(claude_id)")
            .eq("sender_id", self._user_id)
            .eq("status", "pending")
            .execute()
        )
        return [_parse_request_row(row) for row in response.data]

    def respond_to_request(self, request_id: str, accept: bool) -> None:
        """Accept or reject a friend request.

        The auto_create_connection trigger handles connection creation on accept.
        """
        self._require_auth()

        status = "accepted" if accept else "rejected"
        try:
            response = self._supabase.table("requests").update({"status": status}).eq(
                "id", request_id
            ).eq("receiver_id", self._user_id).execute()
            if not response.data:
                raise ValueError("Request not found or already responded to")
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to update request: {exc}") from exc

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    def get_connections(self) -> list[User]:
        """Get all connected users (friends)."""
        self._require_auth()

        # Connections where current user is user_a
        resp_a = (
            self._supabase.table("connections")
            .select("user_b, other:user_b(id, claude_id, public_key, kdf_version, created_at)")
            .eq("user_a", self._user_id)
            .execute()
        )

        # Connections where current user is user_b
        resp_b = (
            self._supabase.table("connections")
            .select("user_a, other:user_a(id, claude_id, public_key, kdf_version, created_at)")
            .eq("user_b", self._user_id)
            .execute()
        )

        users = []
        for row in resp_a.data:
            if isinstance(row.get("other"), dict):
                users.append(_parse_user_row(row["other"]))
        for row in resp_b.data:
            if isinstance(row.get("other"), dict):
                users.append(_parse_user_row(row["other"]))

        return users

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    def send_message(self, receiver_id: str, plaintext: str) -> Message:
        """Encrypt and send a message to a connected user.

        Uses ephemeral sender keys for forward secrecy: a fresh X25519
        keypair is generated per message, and the ephemeral private key
        is discarded immediately after encryption.
        """
        self._require_auth()

        receiver_pub = self._get_receiver_public_key(receiver_id)
        ciphertext, nonce, ephemeral_pub_bytes = encrypt_message_ephemeral(
            receiver_pub, plaintext
        )

        import time

        last_exc = None
        for attempt in range(3):
            try:
                response = (
                    self._supabase.table("messages")
                    .insert(
                        {
                            "sender_id": self._user_id,
                            "receiver_id": receiver_id,
                            "encrypted_content": _bytes_to_db(ciphertext),
                            "nonce": _bytes_to_db(nonce),
                            "ephemeral_public_key": _bytes_to_db(ephemeral_pub_bytes),
                        }
                    )
                    .execute()
                )
                break
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(0.5)
        else:
            raise RuntimeError(f"Failed to send message: {last_exc}") from last_exc

        row = response.data[0]

        # Notify receiver via Pusher (instant delivery)
        if self._realtime:
            self._realtime.publish_message(
                receiver_id,
                {
                    "sender_id": self._user_id,
                    "sender_claude_id": self._claude_id,
                    "message_id": row["id"],
                },
            )

        return Message(
            id=row["id"],
            sender_id=row["sender_id"],
            receiver_id=row["receiver_id"],
            encrypted_content=ciphertext,
            nonce=nonce,
            is_read=row.get("is_read", False),
            created_at=_parse_dt(row.get("created_at")),
            plaintext=plaintext,
            sender_claude_id=self._claude_id,
            ephemeral_public_key=ephemeral_pub_bytes,
        )

    def get_messages(
        self, other_user_id: str, limit: int = 50, before: str | None = None
    ) -> list[Message]:
        """Get conversation messages with another user, decrypted.

        Returns messages ordered by created_at descending.
        """
        self._require_auth()

        # Build query: messages between self and other in both directions
        query = (
            self._supabase.table("messages")
            .select("*")
            .or_(
                f"and(sender_id.eq.{self._user_id},receiver_id.eq.{other_user_id}),"
                f"and(sender_id.eq.{other_user_id},receiver_id.eq.{self._user_id})"
            )
            .order("created_at", desc=True)
            .limit(limit)
        )

        if before is not None:
            query = query.lt("created_at", before)

        response = query.execute()

        other_pub = self._get_receiver_public_key(other_user_id)
        messages = []
        for row in response.data:
            msg = _parse_message_row(row)
            try:
                if msg.ephemeral_public_key is not None:
                    # Forward-secrecy message: use ephemeral key
                    msg.plaintext = decrypt_message_ephemeral(
                        self._private_key, msg.ephemeral_public_key,
                        msg.encrypted_content, msg.nonce,
                    )
                else:
                    # Legacy message: use sender's long-term public key
                    msg.plaintext = decrypt_message(
                        self._private_key, other_pub,
                        msg.encrypted_content, msg.nonce,
                    )
            except Exception:
                msg.plaintext = "[decryption failed]"
            messages.append(msg)

        return messages

    def get_unread_messages(self) -> dict[str, list[Message]]:
        """Get all unread messages grouped by sender claude_id."""
        self._require_auth()

        response = (
            self._supabase.table("messages")
            .select("*, sender:sender_id(claude_id, public_key)")
            .eq("receiver_id", self._user_id)
            .eq("is_read", False)
            .order("created_at", desc=False)
            .execute()
        )

        grouped: dict[str, list[Message]] = {}
        for row in response.data:
            msg = _parse_message_row(row)
            sender_info = row.get("sender", {})
            sender_claude_id = sender_info.get("claude_id", msg.sender_id)
            msg.sender_claude_id = sender_claude_id

            # Decrypt
            try:
                if msg.ephemeral_public_key is not None:
                    # Forward-secrecy message: use ephemeral key
                    msg.plaintext = decrypt_message_ephemeral(
                        self._private_key, msg.ephemeral_public_key,
                        msg.encrypted_content, msg.nonce,
                    )
                else:
                    # Legacy message: use sender's long-term public key
                    sender_pub_bytes = _bytes_from_db(sender_info["public_key"])
                    sender_pub = public_key_from_bytes(sender_pub_bytes)
                    msg.plaintext = decrypt_message(
                        self._private_key, sender_pub,
                        msg.encrypted_content, msg.nonce,
                    )
            except Exception:
                msg.plaintext = "[decryption failed]"

            grouped.setdefault(sender_claude_id, []).append(msg)

        return grouped

    def mark_as_read(self, message_ids: list[str]) -> None:
        """Mark messages as read (only messages where receiver is self)."""
        self._require_auth()

        if not message_ids:
            return

        try:
            (
                self._supabase.table("messages")
                .update({"is_read": True})
                .in_("id", message_ids)
                .eq("receiver_id", self._user_id)
                .execute()
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to mark messages as read: {exc}") from exc

    def get_unread_count(self) -> int:
        """Get total count of unread messages for the current user."""
        self._require_auth()

        response = (
            self._supabase.table("messages")
            .select("id", count="exact")
            .eq("receiver_id", self._user_id)
            .eq("is_read", False)
            .execute()
        )
        return response.count or 0

    # ------------------------------------------------------------------
    # Safety numbers
    # ------------------------------------------------------------------

    def get_safety_number(self, other_user_id: str) -> str:
        """Get the safety number for a conversation with another user."""
        self._require_auth()
        my_pub = get_public_key_bytes(self._private_key)
        other_pub = self._get_receiver_public_key(other_user_id)
        other_pub_bytes = bytes(other_pub)
        return generate_safety_number(my_pub, other_pub_bytes)

    # ------------------------------------------------------------------
    # Public key helper
    # ------------------------------------------------------------------

    def _get_receiver_public_key(self, user_id: str) -> PublicKey:
        """Get a user's public key from cache, or fetch and cache it."""
        if user_id in self._public_key_cache:
            return self._public_key_cache[user_id]

        response = (
            self._supabase.table("users")
            .select("public_key")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not response.data:
            raise ValueError(f"User {user_id} not found")

        pub_bytes = _bytes_from_db(response.data["public_key"])
        pub_key = public_key_from_bytes(pub_bytes)
        self._public_key_cache[user_id] = pub_key
        return pub_key

    # ------------------------------------------------------------------
    # Realtime (Pusher)
    # ------------------------------------------------------------------

    @property
    def realtime(self):
        return self._realtime

    @realtime.setter
    def realtime(self, client):
        self._realtime = client

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @property
    def claude_id(self) -> str | None:
        return self._claude_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_auth(self) -> None:
        """Raise if the client is not authenticated."""
        if self._user_id is None or self._private_key is None:
            raise RuntimeError("Not authenticated. Call register() or login() first.")
