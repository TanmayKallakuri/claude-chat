"""Tests for claude_chat.crypto — key derivation, encryption, decryption."""

import pytest
from nacl.exceptions import CryptoError

from claude_chat.crypto import (
    decrypt_message,
    decrypt_message_ephemeral,
    derive_keypair,
    encrypt_message,
    encrypt_message_ephemeral,
    generate_safety_number,
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


# ---------------------------------------------------------------------------
# Safety numbers
# ---------------------------------------------------------------------------

class TestSafetyNumber:
    def test_deterministic(self, alice, bob):
        """Same keys always produce the same safety number."""
        pub_a = get_public_key_bytes(alice)
        pub_b = get_public_key_bytes(bob)
        sn1 = generate_safety_number(pub_a, pub_b)
        sn2 = generate_safety_number(pub_a, pub_b)
        assert sn1 == sn2

    def test_symmetric(self, alice, bob):
        """Swapping key order gives the same safety number."""
        pub_a = get_public_key_bytes(alice)
        pub_b = get_public_key_bytes(bob)
        sn1 = generate_safety_number(pub_a, pub_b)
        sn2 = generate_safety_number(pub_b, pub_a)
        assert sn1 == sn2

    def test_different_keys_different_number(self, alice, bob):
        """Different key pairs produce different safety numbers."""
        pub_a = get_public_key_bytes(alice)
        pub_b = get_public_key_bytes(bob)
        eve = derive_keypair("eve-secret", "eve@claude")
        pub_e = get_public_key_bytes(eve)
        sn_ab = generate_safety_number(pub_a, pub_b)
        sn_ae = generate_safety_number(pub_a, pub_e)
        assert sn_ab != sn_ae

    def test_output_format(self, alice, bob):
        """Output is 12 groups of 5 digits separated by spaces."""
        pub_a = get_public_key_bytes(alice)
        pub_b = get_public_key_bytes(bob)
        sn = generate_safety_number(pub_a, pub_b)
        groups = sn.split(" ")
        assert len(groups) == 12
        for group in groups:
            assert len(group) == 5
            assert group.isdigit()


# ---------------------------------------------------------------------------
# Ephemeral key encryption (forward secrecy)
# ---------------------------------------------------------------------------

class TestEphemeralEncryption:
    def test_ephemeral_encrypt_decrypt_round_trip(self, bob):
        """Encrypt with ephemeral key, decrypt with receiver's long-term key."""
        bob_pub = public_key_from_bytes(get_public_key_bytes(bob))

        ct, nonce, epk = encrypt_message_ephemeral(bob_pub, "forward secret msg")
        plain = decrypt_message_ephemeral(bob, epk, ct, nonce)
        assert plain == "forward secret msg"

    def test_ephemeral_different_ephemeral_keys_per_message(self, bob):
        """Two encryptions produce different ephemeral public keys."""
        bob_pub = public_key_from_bytes(get_public_key_bytes(bob))

        _, _, epk1 = encrypt_message_ephemeral(bob_pub, "msg1")
        _, _, epk2 = encrypt_message_ephemeral(bob_pub, "msg2")
        assert epk1 != epk2

    def test_ephemeral_sender_private_key_not_needed_for_decrypt(self, alice, bob):
        """Sender's long-term key is NOT used in decryption — only
        the receiver's private key + the ephemeral public key."""
        bob_pub = public_key_from_bytes(get_public_key_bytes(bob))

        ct, nonce, epk = encrypt_message_ephemeral(bob_pub, "secret")

        # Bob decrypts successfully without any reference to alice's keys
        plain = decrypt_message_ephemeral(bob, epk, ct, nonce)
        assert plain == "secret"

        # Eve cannot decrypt even if she knows the ephemeral public key
        eve = derive_keypair("eve-secret", "eve@claude")
        with pytest.raises(CryptoError):
            decrypt_message_ephemeral(eve, epk, ct, nonce)

    def test_backward_compat(self, alice, bob):
        """Old encrypt_message / decrypt_message still work unchanged."""
        bob_pub = public_key_from_bytes(get_public_key_bytes(bob))
        alice_pub = public_key_from_bytes(get_public_key_bytes(alice))

        ct, nonce = encrypt_message(alice, bob_pub, "legacy message")
        plain = decrypt_message(bob, alice_pub, ct, nonce)
        assert plain == "legacy message"
