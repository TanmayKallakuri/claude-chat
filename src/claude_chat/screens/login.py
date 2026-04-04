"""Login / Register screen for claude-chat."""

from __future__ import annotations

import re

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static

from claude_chat.config import (
    MAX_CLAUDE_ID_LENGTH,
    MIN_CLAUDE_ID_LENGTH,
    MIN_PASSPHRASE_LENGTH,
)

_CLAUDE_ID_RE = re.compile(r"^[a-zA-Z0-9_]+$")


class LoginScreen(Screen):
    """Register / Login screen with mode toggle."""

    DEFAULT_CSS = ""  # styles come from login.tcss

    def __init__(self) -> None:
        super().__init__()
        self._mode: str = "register"  # "register" or "login"

    def compose(self) -> ComposeResult:
        with Vertical(id="login-container"):
            yield Static("claude-chat v0.1.0", id="title")

            with Horizontal(id="mode-toggle"):
                yield Button("Register", id="btn-register", variant="primary")
                yield Button("Login", id="btn-login", variant="default")

            yield Label("claude_id", classes="field-label")
            yield Input(
                placeholder="3-20 chars, alphanumeric + underscores",
                id="input-claude-id",
            )

            yield Label("passphrase", classes="field-label")
            yield Input(
                placeholder="min 8 characters",
                id="input-passphrase",
                password=True,
            )

            yield Label("confirm passphrase", id="label-confirm", classes="field-label")
            yield Input(
                placeholder="re-enter passphrase",
                id="input-confirm",
                password=True,
            )

            yield Button("Submit", id="btn-submit", variant="success")

            yield Static(
                "Your passphrase cannot be recovered.\n"
                "If you lose it, you lose your account and messages.",
                id="passphrase-warning",
            )

            yield Label("Ready", id="status")

    def on_mount(self) -> None:
        """Set initial mode and try auto-login from cached session."""
        self._set_mode("register")
        self._try_auto_login()

    # ------------------------------------------------------------------
    # Mode toggle
    # ------------------------------------------------------------------

    def _set_mode(self, mode: str) -> None:
        self._mode = mode

        btn_register = self.query_one("#btn-register", Button)
        btn_login = self.query_one("#btn-login", Button)
        confirm_input = self.query_one("#input-confirm", Input)
        confirm_label = self.query_one("#label-confirm", Label)
        warning = self.query_one("#passphrase-warning", Static)

        if mode == "register":
            btn_register.variant = "primary"
            btn_login.variant = "default"
            confirm_input.display = True
            confirm_label.display = True
            warning.display = True
        else:
            btn_register.variant = "default"
            btn_login.variant = "primary"
            confirm_input.display = False
            confirm_label.display = False
            warning.display = False

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id

        if button_id == "btn-register":
            self._set_mode("register")
        elif button_id == "btn-login":
            self._set_mode("login")
        elif button_id == "btn-submit":
            self._handle_submit()

    # ------------------------------------------------------------------
    # Validation & submission
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Label).update(text)

    def _handle_submit(self) -> None:
        claude_id = self.query_one("#input-claude-id", Input).value.strip()
        passphrase = self.query_one("#input-passphrase", Input).value

        # Validate claude_id
        if not claude_id:
            self._set_status("claude_id is required")
            return
        if len(claude_id) < MIN_CLAUDE_ID_LENGTH:
            self._set_status(
                f"claude_id must be at least {MIN_CLAUDE_ID_LENGTH} characters"
            )
            return
        if len(claude_id) > MAX_CLAUDE_ID_LENGTH:
            self._set_status(
                f"claude_id must be at most {MAX_CLAUDE_ID_LENGTH} characters"
            )
            return
        if not _CLAUDE_ID_RE.match(claude_id):
            self._set_status("claude_id: only letters, numbers, and underscores")
            return

        # Validate passphrase
        if len(passphrase) < MIN_PASSPHRASE_LENGTH:
            self._set_status(
                f"passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters"
            )
            return

        # Validate confirm (register mode)
        if self._mode == "register":
            confirm = self.query_one("#input-confirm", Input).value
            if passphrase != confirm:
                self._set_status("passphrases do not match")
                return

        self._set_status("Connecting...")
        self._do_auth(claude_id, passphrase)

    # ------------------------------------------------------------------
    # Async auth via worker
    # ------------------------------------------------------------------

    @work(thread=True)
    def _do_auth(self, claude_id: str, passphrase: str) -> None:
        """Run register/login in a background thread."""
        from claude_chat.session import Session, save_session
        from claude_chat.supabase_client import ChatClient

        client = ChatClient()

        try:
            if self._mode == "register":
                user_id = client.register(claude_id, passphrase)
            else:
                user_id = client.login(claude_id, passphrase)
        except (ValueError, RuntimeError) as exc:
            self.app.call_from_thread(self._set_status, str(exc))
            return

        # Persist session
        save_session(Session(claude_id=claude_id, passphrase=passphrase, user_id=user_id))

        # Store client on the app so other screens can use it
        self.app.client = client  # type: ignore[attr-defined]

        self.app.call_from_thread(self._on_auth_success, claude_id)

    def _on_auth_success(self, claude_id: str) -> None:
        """Transition to the main screen after successful auth."""
        from claude_chat.screens.main import MainScreen

        self._set_status(f"Logged in as {claude_id}!")
        self.app.push_screen(MainScreen())

    # ------------------------------------------------------------------
    # Auto-login from cached session
    # ------------------------------------------------------------------

    def _try_auto_login(self) -> None:
        """If a session file exists, pre-fill fields and attempt login."""
        from claude_chat.session import load_session

        session = load_session()
        if session is None:
            return

        self.query_one("#input-claude-id", Input).value = session.claude_id
        self.query_one("#input-passphrase", Input).value = session.passphrase
        self._set_mode("login")
        self._set_status("Resuming session...")
        self._do_auth(session.claude_id, session.passphrase)
