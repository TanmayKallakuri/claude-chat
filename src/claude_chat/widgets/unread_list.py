"""Unread messages list widget, grouped by sender."""

from __future__ import annotations

from textual import on, work
from textual.message import Message as TMessage
from textual.containers import Container
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


class UnreadList(Container):
    """Shows unread messages grouped by sender.

    Each item displays the sender's claude_id, unread count, and latest
    message preview.  Selecting an item posts an ``OpenChat`` message so the
    parent screen can push a ChatView.
    """

    DEFAULT_CSS = """
    UnreadList {
        width: 100%;
        height: 100%;
    }

    UnreadList #unread-empty {
        width: 100%;
        height: auto;
        content-align: center middle;
        color: #888888;
        padding: 2;
    }

    UnreadList OptionList {
        width: 100%;
        height: 100%;
        background: #1a1a2e;
    }
    """

    class OpenChat(TMessage):
        """Request to open a chat with a specific user."""

        def __init__(self, user_id: str, claude_id: str) -> None:
            self.user_id = user_id
            self.claude_id = claude_id
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._user_map: dict = {}

    def compose(self):
        yield Static("All caught up! No unread messages.", id="unread-empty")
        yield OptionList(id="unread-option-list")

    def on_mount(self) -> None:
        self.query_one("#unread-option-list", OptionList).display = False

    def update_data(self, grouped: dict[str, list]) -> None:
        """Refresh the list with grouped unread messages.

        ``grouped`` maps sender claude_id -> list of Message objects.
        Each Message must have ``.sender_id`` and ``.plaintext``.
        """
        option_list = self.query_one("#unread-option-list", OptionList)
        empty_label = self.query_one("#unread-empty", Static)

        option_list.clear_options()
        self._user_map: dict[int, tuple[str, str]] = {}  # index -> (user_id, claude_id)

        if not grouped:
            empty_label.display = True
            option_list.display = False
            return

        empty_label.display = False
        option_list.display = True

        idx = 0
        for claude_id, messages in grouped.items():
            count = len(messages)
            latest = messages[-1]
            preview = (latest.plaintext or "")[:60]
            label = f"{claude_id} ({count} unread)\n  > {preview}"
            option_list.add_option(Option(label, id=str(idx)))
            self._user_map[idx] = (latest.sender_id, claude_id)
            idx += 1

    @on(OptionList.OptionSelected, "#unread-option-list")
    def _on_selected(self, event: OptionList.OptionSelected) -> None:
        idx = int(event.option.id)
        if idx in self._user_map:
            user_id, claude_id = self._user_map[idx]
            self.post_message(self.OpenChat(user_id, claude_id))
