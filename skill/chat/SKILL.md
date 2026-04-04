---
name: chat
description: Launch claude-chat, an encrypted social messaging TUI for Claude Code users. Connect with friends, send messages, and chat in real-time — all from the terminal.
---

# claude-chat

Launch the encrypted social chat interface.

## Instructions

When the user invokes /chat, run the following command to launch the chat TUI:

```bash
claude-chat
```

If `claude-chat` is not installed, install it first:

```bash
pip install claude-chat
```

If the user is running from the source repository:

```bash
cd ~/claude-chat && pip install -e . && claude-chat
```

## Notes

- This launches an interactive terminal UI — it will take over the terminal
- The chat uses end-to-end encryption; messages are unreadable on the server
- No Claude API usage — this is a standalone social feature
- First-time users will be asked to create a username and passphrase
