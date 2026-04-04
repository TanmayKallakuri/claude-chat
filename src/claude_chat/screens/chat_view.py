"""Individual conversation screen."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Static

from claude_chat.widgets.message_line import MessageLine


class ChatView(Screen):
    """Full-screen conversation view with a single contact.

    Pushed onto the screen stack when a user selects a conversation from
    the Unread or Read tabs.
    """

    BINDINGS = [("escape", "go_back", "Back")]

    def __init__(self, user_id: str, claude_id: str) -> None:
        self.other_user_id = user_id
        self.other_claude_id = claude_id
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Static(f" Chat with {self.other_claude_id} ", id="chat-header")
        yield VerticalScroll(id="message-container")
        yield Input(placeholder="Type a message...", id="message-input")

    def on_mount(self) -> None:
        self.load_messages()

    # ------------------------------------------------------------------
    # Message loading
    # ------------------------------------------------------------------

    @work(thread=True)
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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send message on Enter."""
        text = event.value.strip()
        if text:
            event.input.clear()
            self.notify("Sending...", severity="information")
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
    # Real-time incoming messages
    # ------------------------------------------------------------------

    def append_realtime_message(self, msg) -> None:
        """Append a message received via realtime subscription and mark it read.

        Called from MainScreen._handle_realtime_message on the main thread.
        """
        try:
            container = self.query_one("#message-container", VerticalScroll)
        except Exception:
            return  # Screen no longer mounted

        timestamp = ""
        if msg.created_at is not None:
            timestamp = msg.created_at.strftime("%H:%M")

        container.mount(
            MessageLine(
                timestamp=timestamp,
                sender=self.other_claude_id,
                text=msg.plaintext or "[encrypted]",
                is_self=False,
            )
        )
        container.scroll_end(animate=False)

        # Mark as read immediately since the chat is open
        self._mark_ids_as_read([msg.id])

    @work(thread=True)
    def _mark_ids_as_read(self, message_ids: list[str]) -> None:
        """Mark specific message IDs as read in a worker thread."""
        try:
            self.app.client.mark_as_read(message_ids)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        """Pop back to the main screen."""
        self.app.pop_screen()
