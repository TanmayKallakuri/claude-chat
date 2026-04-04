# claude-chat

A CLI chat app that makes Claude Code social. Connect with friends, share what you're working on, and message in real-time — all from the terminal.

## What it does

- **Find friends** by their unique claude_id and send connection requests
- **Chat in real-time** with end-to-end encrypted messages
- **Stay in flow** — a lightweight TUI that feels like the terminal, not a web app
- **Zero Claude API usage** — this is purely a social layer, no AI involved

## How it works

```
$ claude-chat

  ┌─────────────────────────────────────────┐
  │  claude-chat v0.1.0                     │
  │                                         │
  │  [Unread] [Read] [Requests] [Search]    │
  │                                         │
  │  > tanmay_k: hey, check out this repo   │
  │  > dev_friend: nice, sending a PR now   │
  │  > you: looks good, merging             │
  │                                         │
  │  > _                                    │
  └─────────────────────────────────────────┘
```

## Getting started

```bash
pip install claude-chat
claude-chat
```

On first launch, you'll pick a **claude_id** (your username) and a **passphrase**. The passphrase is used for login _and_ to derive your encryption keys — there's no password reset, so pick something you'll remember.

## Features

| Feature | Details |
|---------|---------|
| Encryption | X25519 + XSalsa20-Poly1305 (via PyNaCl) |
| Forward secrecy | Per-message ephemeral keys — past messages safe if key leaks |
| Key derivation | Argon2id from your passphrase — private key never leaves your machine |
| Session storage | Encrypted with device-bound key (NaCl SecretBox) |
| Contact verification | Safety numbers (F2 in chat) — verify who you're talking to |
| Session expiry | Auto-logout after 7 days of inactivity |
| Messages | Text and links only — no images or videos |
| Requests | 3 friend requests per day to prevent spam |
| Notifications | Chime sound on new messages and requests |
| Multi-device | Same claude_id + passphrase works on any machine |

## Security model

Your passphrase derives a deterministic X25519 keypair via Argon2id. The public key is stored on the server; the private key only exists in memory during your session. Messages are encrypted client-side before they touch the network — the server stores ciphertext it cannot read.

**Forward secrecy:** Each message is encrypted with a fresh ephemeral X25519 keypair. The ephemeral private key is discarded immediately after encryption. Even if your passphrase is later compromised, past messages cannot be decrypted — the ephemeral keys no longer exist.

**Contact verification:** Press F2 in any chat to see a 60-digit safety number. Compare it with your contact out-of-band (call, in-person) to verify you're not being intercepted.

**Session protection:** Your passphrase is encrypted on disk with a device-bound key (NaCl SecretBox). An attacker needs both your session file and device key to recover credentials. Sessions auto-expire after 7 days.

**Tradeoffs to know about:**
- Lose your passphrase = lose your account + message history (no recovery)
- Passphrase cannot be changed in v1 (changing it would change your keys)
- Server can see message metadata (sender, receiver, timestamps) but not content

## Tech stack

- **Python 3.13** + **Textual** — terminal UI
- **Supabase** — auth, database, realtime subscriptions
- **PyNaCl** — libsodium bindings for encryption
- **Argon2-cffi** — passphrase key derivation

## Development

```bash
git clone https://github.com/TanmayKallakuri/claude-chat.git
cd claude-chat
pip install -e ".[dev]"
pytest
```

## Status

Building in public. Current progress:

- [x] Phase 1: Foundation (crypto, models, config, session) — 35 tests
- [x] Phase 2: Supabase backend (schema, RLS, client) — 16 tests
- [x] Phase 3: TUI auth flow (register/login with auto-login)
- [x] Phase 4: TUI main interface (4 tabs, chat view, 5 widgets)
- [x] Phase 5: Real-time subscriptions, polling fallback, sound notifications
- [x] Phase 6: Claude Code `/chat` skill, UX polish, empty states
