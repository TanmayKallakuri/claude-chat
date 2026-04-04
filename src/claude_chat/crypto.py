"""End-to-end encryption primitives for claude-chat.

Key derivation, message encryption/decryption using X25519 + XSalsa20-Poly1305.
"""

import hashlib

from argon2.low_level import hash_secret_raw, Type
from nacl.public import Box, PrivateKey, PublicKey

KDF_VERSION = 1
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MiB
ARGON2_PARALLELISM = 1
ARGON2_HASH_LEN = 32


def derive_keypair(passphrase: str, claude_id: str) -> PrivateKey:
    """Derive a deterministic X25519 keypair from passphrase + claude_id.

    Salt is the first 16 bytes of SHA-256(claude_id).
    Argon2id produces a 32-byte seed that becomes an X25519 private key.
    """
    salt = hashlib.sha256(claude_id.encode("utf-8")).digest()[:16]
    seed = hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )
    return PrivateKey(seed)


def get_public_key_bytes(private_key: PrivateKey) -> bytes:
    """Return the raw 32-byte public key for storage/transmission."""
    return bytes(private_key.public_key)


def public_key_from_bytes(raw: bytes) -> PublicKey:
    """Reconstruct a PublicKey from raw bytes."""
    return PublicKey(raw)


def encrypt_message(
    sender_private: PrivateKey,
    receiver_public: PublicKey,
    plaintext: str,
) -> tuple[bytes, bytes]:
    """Encrypt a plaintext string for a recipient.

    Returns (ciphertext, nonce).
    """
    box = Box(sender_private, receiver_public)
    encrypted = box.encrypt(plaintext.encode("utf-8"))
    # nacl EncryptedMessage: nonce (24 bytes) || ciphertext
    nonce = encrypted.nonce
    ciphertext = encrypted.ciphertext
    return ciphertext, nonce


def decrypt_message(
    receiver_private: PrivateKey,
    sender_public: PublicKey,
    ciphertext: bytes,
    nonce: bytes,
) -> str:
    """Decrypt ciphertext back to a plaintext string."""
    box = Box(receiver_private, sender_public)
    plaintext_bytes = box.decrypt(ciphertext, nonce)
    return plaintext_bytes.decode("utf-8")
