"""Main Textual application for claude-chat."""

from textual.app import App
from textual.binding import Binding

from claude_chat.screens.login import LoginScreen


class ClaudeChatApp(App):
    """claude-chat: Encrypted social chat for Claude Code users."""

    TITLE = "claude-chat"
    CSS_PATH = [
        "styles/app.tcss",
        "styles/login.tcss",
        "styles/main.tcss",
        "styles/chat.tcss",
    ]
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True)]

    SCREENS = {"login": LoginScreen}

    # Set by LoginScreen after successful auth; other screens read this.
    client = None  # type: ignore[assignment]

    def on_mount(self) -> None:
        """Check for existing session on startup."""
        from claude_chat.session import load_session

        session = load_session()
        if session:
            # Try auto-login with cached credentials
            self.push_screen("login")
        else:
            self.push_screen("login")
