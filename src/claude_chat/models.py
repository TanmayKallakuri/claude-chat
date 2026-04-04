from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime


def _bytes_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64_to_bytes(data) -> bytes:
    if data is None:
        raise ValueError("Expected base64 string, got None")
    if isinstance(data, bytes):
        return data
    if not isinstance(data, str):
        raise ValueError(f"Expected base64 string, got {type(data).__name__}")
    return base64.b64decode(data)


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    if isinstance(s, datetime):
        return s
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


@dataclass
class User:
    id: str
    claude_id: str
    public_key: bytes
    kdf_version: int = 1
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "claude_id": self.claude_id,
            "public_key": _bytes_to_b64(self.public_key),
            "kdf_version": self.kdf_version,
            "created_at": _dt_to_str(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: dict) -> User:
        return cls(
            id=data["id"],
            claude_id=data["claude_id"],
            public_key=_b64_to_bytes(data["public_key"]),
            kdf_version=data.get("kdf_version", 1),
            created_at=_str_to_dt(data.get("created_at")),
        )


@dataclass
class ConnectionRequest:
    id: str
    sender_id: str
    receiver_id: str
    status: str = "pending"  # pending, accepted, rejected
    created_at: datetime | None = None
    # Optional: populated by joins
    sender_claude_id: str | None = None
    receiver_claude_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "status": self.status,
            "created_at": _dt_to_str(self.created_at),
            "sender_claude_id": self.sender_claude_id,
            "receiver_claude_id": self.receiver_claude_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConnectionRequest:
        return cls(
            id=data["id"],
            sender_id=data["sender_id"],
            receiver_id=data["receiver_id"],
            status=data.get("status", "pending"),
            created_at=_str_to_dt(data.get("created_at")),
            sender_claude_id=data.get("sender_claude_id"),
            receiver_claude_id=data.get("receiver_claude_id"),
        )


@dataclass
class Connection:
    id: str
    user_a: str
    user_b: str
    created_at: datetime | None = None
    # Optional: the other user's info (populated by app logic)
    other_user: User | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_a": self.user_a,
            "user_b": self.user_b,
            "created_at": _dt_to_str(self.created_at),
            "other_user": self.other_user.to_dict() if self.other_user else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Connection:
        other_user_data = data.get("other_user")
        return cls(
            id=data["id"],
            user_a=data["user_a"],
            user_b=data["user_b"],
            created_at=_str_to_dt(data.get("created_at")),
            other_user=User.from_dict(other_user_data) if isinstance(other_user_data, dict) else None,
        )


@dataclass
class Message:
    id: str
    sender_id: str
    receiver_id: str
    encrypted_content: bytes
    nonce: bytes
    is_read: bool = False
    created_at: datetime | None = None
    # Decrypted content (populated client-side, never stored)
    plaintext: str | None = None
    # Optional: sender info
    sender_claude_id: str | None = None
    # Forward secrecy: ephemeral public key (None for legacy messages)
    ephemeral_public_key: bytes | None = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "encrypted_content": _bytes_to_b64(self.encrypted_content),
            "nonce": _bytes_to_b64(self.nonce),
            "is_read": self.is_read,
            "created_at": _dt_to_str(self.created_at),
        }
        if self.ephemeral_public_key is not None:
            d["ephemeral_public_key"] = _bytes_to_b64(self.ephemeral_public_key)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Message:
        epk = data.get("ephemeral_public_key")
        return cls(
            id=data["id"],
            sender_id=data["sender_id"],
            receiver_id=data["receiver_id"],
            encrypted_content=_b64_to_bytes(data["encrypted_content"]),
            nonce=_b64_to_bytes(data["nonce"]),
            is_read=data.get("is_read", False),
            created_at=_str_to_dt(data.get("created_at")),
            plaintext=data.get("plaintext"),
            sender_claude_id=data.get("sender_claude_id"),
            ephemeral_public_key=_b64_to_bytes(epk) if epk is not None else None,
        )
