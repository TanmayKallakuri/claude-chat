# claude-chat — Encrypted Social Chat for Claude Code

## Context

Claude Code is a powerful dev tool but has no social layer. This project adds a `/chat` command that opens a CLI-style encrypted chat TUI where users can connect with friends by "claude_id", share what they're working on, and message in real-time — all without touching the Claude API.

---

## Tech Stack

- **Python 3.13** + **Textual** (TUI)
- **Supabase** (new project — auth, database, realtime)
- **PyNaCl** (X25519 + XSalsa20-Poly1305 encryption)
- **Argon2-cffi** (passphrase → key derivation)
- **winsound / afplay** (notification chimes, no extra deps)

---

## Project Structure

```
~/claude-chat/
├── pyproject.toml
├── tests/
│   ├── test_crypto.py
│   ├── test_session.py
│   ├── test_supabase_client.py
│   └── test_models.py
├── assets/
│   ├── chime_message.wav
│   └── chime_request.wav
├── skill/
│   └── chat/SKILL.md          # Claude Code /chat skill
└── src/claude_chat/
    ├── __init__.py
    ├── __main__.py             # CLI entry: `claude-chat`
    ├── app.py                  # Textual App, screen routing
    ├── config.py               # Supabase URL/key, paths, constants
    ├── crypto.py               # KDF, keypair derivation, encrypt/decrypt
    ├── session.py              # Local session cache (~/.claude/chat/)
    ├── supabase_client.py      # Auth, CRUD, realtime subscriptions
    ├── models.py               # User, Message, Request, Connection dataclasses
    ├── notifications.py        # Sound chimes (winsound on Win, afplay on Mac)
    ├── screens/
    │   ├── login.py            # Register / login form
    │   ├── main.py             # Tabbed main screen (4 tabs)
    │   └── chat_view.py        # Individual conversation view
    ├── widgets/
    │   ├── unread_list.py      # Unread messages grouped by sender
    │   ├── read_list.py        # All connections + chat history
    │   ├── requests_panel.py   # Incoming/outgoing friend requests
    │   ├── search_panel.py     # Search users + send request
    │   └── message_line.py     # Single message: [time] user: text
    └── styles/
        └── *.tcss              # Minimal CLI-aesthetic styling
```

---

## Supabase Schema

**Auth:** Use Supabase Auth with `{claude_id}@claude-chat.local` as email + passphrase as password. This gives us JWTs and RLS for free.

### Tables

```sql
users        (id, claude_id UNIQUE, public_key, kdf_version, created_at)
requests     (id, sender_id, receiver_id, status, created_at)  -- UNIQUE(sender,receiver)
connections  (id, user_a, user_b, created_at)                   -- CHECK(user_a < user_b)
messages     (id, sender_id, receiver_id, encrypted_content, nonce, is_read, created_at)
```

**Rate limiting:** Postgres trigger on `requests` — max 3 inserts per sender per 24h.  
**RLS:** Users can only read their own messages/requests/connections. Only sender can insert messages. Only receiver can accept/reject requests or mark messages as read.

---

## Encryption Design

1. **Registration:** `passphrase + claude_id` → Argon2id KDF → 32-byte seed → X25519 keypair
2. **Public key** stored in Supabase `users` table. Private key **never leaves the client** — derived fresh from passphrase each session.
3. **Sending:** PyNaCl `Box(sender_private, receiver_public)` → XSalsa20-Poly1305 encrypted message + nonce → stored in Supabase
4. **Receiving:** `Box(receiver_private, sender_public)` → decrypt
5. **KDF params locked** — store `kdf_version` in users table for future migration path
6. **No passphrase change in v1** — changing it changes the keypair, breaks all history. Document clearly.
7. **Session cache:** passphrase stored in `~/.claude/chat/session.json` with file permissions `600`. User doesn't re-enter on same device.

---

## Build Phases

### Phase 1: Foundation (no network, no UI)
- `config.py` — paths, constants
- `models.py` — dataclasses with serialization
- `crypto.py` — KDF, keypair, encrypt/decrypt **(most critical — build + test first)**
- `session.py` — save/load local session
- **Tests:** crypto round-trips, session persistence, model serialization

### Phase 2: Supabase Backend
- Create Supabase project (via MCP tools)
- Run schema migrations (tables, indexes, RLS, triggers)
- `supabase_client.py` — `ChatClient` class with:
  - `register()`, `login()` (via Supabase Auth)
  - `search_users()`, `send_request()`, `respond_to_request()`
  - `send_message()`, `get_messages()`, `get_unread_messages()`, `mark_as_read()`
  - `subscribe_messages()`, `subscribe_requests()` (Supabase Realtime)
- **Tests:** integration tests against Supabase

### Phase 3: TUI — Auth Flow
- `app.py` — Textual App with session check on mount
- `screens/login.py` — register/login form with passphrase warning
- **Test:** app launches, register works, login works, session persists

### Phase 4: TUI — Main Interface
- `screens/main.py` — `TabbedContent` with 4 tabs
- All widgets: `unread_list`, `read_list`, `requests_panel`, `search_panel`
- `screens/chat_view.py` — conversation view with input box
- `message_line.py` — simple `[HH:MM] user: text` format
- **Test:** navigate tabs, open conversations, send/receive messages

### Phase 5: Real-time & Notifications
- Wire Supabase Realtime subscriptions into MainScreen
- `notifications.py` — chime sounds on new message + new request
- Unread badge updates on tab headers
- Auto-scroll in chat view on new message
- Mark-as-read when conversation is opened
- **Test:** two clients, send message, verify real-time delivery + sound

### Phase 6: Polish & Packaging
- `pyproject.toml` with `claude-chat` entry point
- `skill/chat/SKILL.md` for Claude Code `/chat` integration
- Edge cases: rate limit feedback in UI, empty states, connection errors
- `pip install -e .` and verify full flow

---

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Auth | Supabase Auth (email=`{id}@claude-chat.local`) | Get JWTs + RLS for free, no custom auth server |
| Encryption | PyNaCl Box (X25519 + XSalsa20-Poly1305) | Battle-tested, deterministic from passphrase |
| Salt for KDF | `SHA256(claude_id)[:16]` | Unique, stable, reproducible across devices |
| Real-time | Supabase Realtime with polling fallback | Python Realtime client less mature than JS — need fallback |
| Sound | `winsound` (Win) / `afplay` (Mac) | Zero extra dependencies |
| No passphrase change v1 | Defer key rotation to v2 | Massive complexity, not needed for MVP |
| Text only | No images/videos, links allowed | Keeps encryption simple, reduces storage |

---

## Verification Plan

1. **Unit tests:** `pytest tests/` — crypto, session, models
2. **Integration tests:** register two users, send request, accept, exchange messages, verify encryption/decryption
3. **Manual E2E test:**
   - Terminal 1: `claude-chat` → register as `user_a`
   - Terminal 2: `claude-chat` → register as `user_b`
   - `user_a` searches for `user_b`, sends request
   - `user_b` sees request in Requests tab, accepts
   - Both can now chat — verify real-time delivery and chime sounds
   - Close and reopen — verify session persistence and message history
4. **Claude Code integration:** install skill, run `/chat`, verify it launches the TUI
