"""Entry point for `python -m claude_chat`."""

import sys


def _ensure_setup() -> bool:
    """Check that required secrets are configured. Prompt if missing."""
    from claude_chat.config import PUSHER_SECRET, ENV_FILE, ensure_chat_dir

    if PUSHER_SECRET:
        return True

    print("=" * 50)
    print("  claude-chat — first-time setup")
    print("=" * 50)
    print()
    print("You need a Pusher secret to enable real-time messaging.")
    print("Ask the person who invited you for the secret key.")
    print()

    secret = input("Pusher secret: ").strip()
    if not secret:
        print("No secret provided. Exiting.")
        return False

    ensure_chat_dir()

    # Read existing .env or start fresh
    lines = []
    if ENV_FILE.is_file():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    # Remove any old PUSHER_SECRET line
    lines = [l for l in lines if not l.strip().startswith("PUSHER_SECRET")]
    lines.append(f"PUSHER_SECRET={secret}")

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print()
    print("Saved! Starting claude-chat...")
    print()

    # Reload the secret into the environment
    import os
    os.environ["PUSHER_SECRET"] = secret

    return True


def main():
    if not _ensure_setup():
        sys.exit(1)

    from claude_chat.app import ClaudeChatApp

    app = ClaudeChatApp()
    app.run()


if __name__ == "__main__":
    main()
