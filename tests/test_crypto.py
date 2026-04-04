"""Tests for claude_chat.crypto — key derivation, encryption, decryption."""

import pytest
from nacl.exceptions import CryptoError

from claude_chat.crypto import (
    decrypt_message,
    derive_keypair,
    encrypt_message,
    get_public_key_bytes,
    public_key_from_bytes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def alice():
    return derive_keypair("alice-secret", "alice@claude")


@pytest.fixture()
def bob():
    return derive_keypair("bob-secret", "bob@claude")


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

class TestDeriveKeypair:
    def test_deterministic(self):
        """Same passphrase + claude_id always produces the same key."""
        k1 = derive_keypair("pass", "user1")
        k2 = derive_keypair("pass", "user1")
        assert bytes(k1) == bytes(k2)
        assert get_public_key_bytes(k1) == get_public_key_bytes(k2)

    def test_different_passphrase(self):
        k1 = derive_keypair("pass-a", "user1")
        k2 = derive_keypair("pass-b", "user1")
        assert bytes(k1) != bytes(k2)

    def test_different_claude_id(self):
        k1 = derive_keypair("pass", "user1")
        k2 = derive_keypair("pass", "user2")
        assert bytes(k1) != bytes(k2)

    def test_key_length(self):
        k = derive_keypair("x", "y")
        assert len(bytes(k)) == 32
        assert len(get_public_key_bytes(k)) == 32


# ---------------------------------------------------------------------------
# Public key serialization
# ---------------------------------------------------------------------------

class TestPublicKeySerialization:
    def test_round_trip(self, alice):
        raw = get_public_key_bytes(alice)
        restored = public_key_from_bytes(raw)
        assert bytes(restored) == raw

    def test_bytes_length(self, alice):
        assert len(get_public_key_bytes(alice)) == 32


# ---------------------------------------------------------------------------
# Encrypt / decrypt
# ---------------------------------------------------------------------------

class TestEncryptDecrypt:
    def test_round_trip(self, alice):
        """Sender encrypts and decrypts their own message (same Box)."""
        pub = public_key_from_bytes(get_public_key_bytes(alice))
        ct, nonce = encrypt_message(alice, pub, "hello")
        plain = decrypt_message(alice, pub, ct, nonce)
        assert plain == "hello"

    def test_cross_user(self, alice, bob):
        """Alice encrypts for Bob; Bob decrypts with Alice's public key."""
        bob_pub = public_key_from_bytes(get_public_key_bytes(bob))
        alice_pub = public_key_from_bytes(get_public_key_bytes(alice))

        ct, nonce = encrypt_message(alice, bob_pub, "secret for bob")
        plain = decrypt_message(bob, alice_pub, ct, nonce)
        assert plain == "secret for bob"

    def test_wrong_key_fails(self, alice, bob):
        """Decrypting with a wrong key must raise CryptoError."""
        bob_pub = public_key_from_bytes(get_public_key_bytes(bob))
        ct, nonce = encrypt_message(alice, bob_pub, "no peeking")

        eve = derive_keypair("eve-secret", "eve@claude")
        eve_pub = public_key_from_bytes(get_public_key_bytes(eve))

        with pytest.raises(CryptoError):
            decrypt_message(eve, eve_pub, ct, nonce)

    def test_empty_string(self, alice):
        pub = public_key_from_bytes(get_public_key_bytes(alice))
        ct, nonce = encrypt_message(alice, pub, "")
        assert decrypt_message(alice, pub, ct, nonce) == ""

    def test_unicode_message(self, alice, bob):
        bob_pub = public_key_from_bytes(get_public_key_bytes(bob))
        alice_pub = public_key_from_bytes(get_public_key_bytes(alice))

        msg = "こんにちは 🔐 Ñoño café"
        ct, nonce = encrypt_message(alice, bob_pub, msg)
        assert decrypt_message(bob, alice_pub, ct, nonce) == msg

    def test_long_message(self, alice):
        pub = public_key_from_bytes(get_public_key_bytes(alice))
        msg = "a" * 100_000
        ct, nonce = encrypt_message(alice, pub, msg)
        assert decrypt_message(alice, pub, ct, nonce) == msg

    def test_nonce_is_unique(self, alice):
        """Each encryption should produce a different nonce."""
        pub = public_key_from_bytes(get_public_key_bytes(alice))
        _, n1 = encrypt_message(alice, pub, "msg")
        _, n2 = encrypt_message(alice, pub, "msg")
        assert n1 != n2
