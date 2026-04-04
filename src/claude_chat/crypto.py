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


def generate_safety_number(public_key_a: bytes, public_key_b: bytes) -> str:
    """Generate a safety number from two public keys.

    The safety number is the same regardless of which key is "a" or "b"
    (we sort them first). This produces a 60-digit number split into
    12 groups of 5 digits, like Signal does.
    """
    # Sort keys so order doesn't matter
    keys = sorted([public_key_a, public_key_b])
    combined = keys[0] + keys[1]

    # Hash with SHA-512 for enough bits
    digest = hashlib.sha512(combined).digest()

    # Convert first 30 bytes to decimal digits (60 digits)
    number = int.from_bytes(digest[:30], "big")
    digits = str(number).zfill(60)[:60]

    # Format as 12 groups of 5
    groups = [digits[i:i+5] for i in range(0, 60, 5)]
    return " ".join(groups)


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


# ---------------------------------------------------------------------------
# Forward secrecy: ephemeral sender keys
# ---------------------------------------------------------------------------


def encrypt_message_ephemeral(
    receiver_public: PublicKey, plaintext: str
) -> tuple[bytes, bytes, bytes]:
    """Encrypt with a fresh ephemeral keypair for forward secrecy.

    Returns (ciphertext, nonce, ephemeral_public_key_bytes).
    The ephemeral private key exists only in this function scope
    and is garbage collected after return.
    """
    ephemeral_private = PrivateKey.generate()
    ephemeral_public_bytes = bytes(ephemeral_private.public_key)

    box = Box(ephemeral_private, receiver_public)
    encrypted = box.encrypt(plaintext.encode("utf-8"))

    # ephemeral_private goes out of scope and is garbage collected
    return encrypted.ciphertext, encrypted.nonce, ephemeral_public_bytes


def decrypt_message_ephemeral(
    receiver_private: PrivateKey,
    ephemeral_public_bytes: bytes,
    ciphertext: bytes,
    nonce: bytes,
) -> str:
    """Decrypt a message that was encrypted with an ephemeral key.

    The receiver uses their long-term private key + the sender's
    ephemeral public key (included with the message).
    """
    ephemeral_public = PublicKey(ephemeral_public_bytes)
    box = Box(receiver_private, ephemeral_public)
    return box.decrypt(ciphertext, nonce).decode("utf-8")
