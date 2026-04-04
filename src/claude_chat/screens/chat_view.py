"""Individual conversation screen."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.binding import Binding
from textual.widgets import Input, Static, TextArea

from claude_chat.widgets.message_line import MessageLine


class ChatView(Screen):
    """Full-screen conversation view with a single contact.

    Pushed onto the screen stack when a user selects a conversation from
    the Unread or Read tabs.
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("f2", "show_safety_number", "Verify"),
        Binding("ctrl+s", "send_input", "Send", show=True),
    ]

    def __init__(self, user_id: str, claude_id: str) -> None:
        self.other_user_id = user_id
        self.other_claude_id = claude_id
        self._last_message_count = 0
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static(f" Chat with {self.other_claude_id} ", id="chat-header")
        yield VerticalScroll(id="message-container")
        yield TextArea(id="message-input")

    def on_mount(self) -> None:
        self.load_messages()

    # ------------------------------------------------------------------
    # Message loading
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True)
    def load_messages(self) -> None:
        """Fetch conversation history and mark unread as read."""
        client = self.app.client

        try:
            messages = client.get_messages(self.other_user_id)
        except Exception as exc:
            self.app.call_from_thread(
                self.notify, f"Failed to load messages: {exc}", severity="error"
            )
            return

        # Messages come newest-first; reverse for display
        messages.reverse()

        # Skip re-render if nothing changed (avoids flicker during polling)
        msg_count = len(messages)
        if msg_count == self._last_message_count and msg_count > 0:
            return
        self._last_message_count = msg_count

        # Mark unread messages as read
        unread_ids = [
            m.id
            for m in messages
            if not m.is_read and m.sender_id == self.other_user_id
        ]
        if unread_ids:
            try:
                client.mark_as_read(unread_ids)
            except Exception:
                pass

        self.app.call_from_thread(self._render_messages, messages)

    def _render_messages(self, messages: list) -> None:
        """Mount MessageLine widgets into the scroll container."""
        try:
            container = self.query_one("#message-container", VerticalScroll)
        except Exception:
            return  # Screen may have been popped
        container.remove_children()

        if not messages:
            container.mount(
                Static(
                    "No messages yet. Say hi!",
                    id="empty-chat-placeholder",
                )
            )
            return

        my_id = self.app.client.user_id

        for msg in messages:
            timestamp = ""
            if msg.created_at is not None:
                timestamp = msg.created_at.strftime("%H:%M")

            is_self = msg.sender_id == my_id
            sender = self.app.client.claude_id if is_self else self.other_claude_id
            text = msg.plaintext or "[encrypted]"

            container.mount(
                MessageLine(
                    timestamp=timestamp,
                    sender=sender,
                    text=text,
                    is_self=is_self,
                )
            )

        # Scroll to bottom
        container.scroll_end(animate=False)

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------

    def action_send_input(self) -> None:
        """Send message on Ctrl+S."""
        try:
            ta = self.query_one("#message-input", TextArea)
        except Exception:
            return
        text = ta.text.strip()
        if text:
            ta.clear()
            self.send_message(text)

    @work(thread=True)
    def send_message(self, text: str) -> None:
        """Encrypt and send a message in a worker thread."""
        client = self.app.client
        try:
            msg = client.send_message(self.other_user_id, text)
        except Exception as exc:
            self.app.call_from_thread(
                self.notify, f"Send failed: {exc}", severity="error"
            )
            return

        self.app.call_from_thread(self._append_message, msg)

    def _append_message(self, msg) -> None:
        """Add a sent message to the container and scroll down."""
        try:
            container = self.query_one("#message-container", VerticalScroll)
        except Exception:
            return  # Screen may have been popped

        # Remove empty-chat placeholder if present
        try:
            placeholder = container.query_one("#empty-chat-placeholder", Static)
            placeholder.remove()
        except Exception:
            pass

        timestamp = ""
        if msg.created_at is not None:
            timestamp = msg.created_at.strftime("%H:%M")

        container.mount(
            MessageLine(
                timestamp=timestamp,
                sender=self.app.client.claude_id,
                text=msg.plaintext or "",
                is_self=True,
            )
        )
        container.scroll_end(animate=False)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_show_safety_number(self) -> None:
        """Display the safety number for this conversation."""
        try:
            safety_number = self.app.client.get_safety_number(self.other_user_id)
            self.notify(
                f"Safety number with {self.other_claude_id}:\n{safety_number}\n\n"
                "Compare this with your contact to verify identity.",
                severity="information",
                timeout=15,
            )
        except Exception as exc:
            self.notify(f"Could not generate safety number: {exc}", severity="error")

    def action_go_back(self) -> None:
        """Pop back to the main screen."""
        self.app.pop_screen()
