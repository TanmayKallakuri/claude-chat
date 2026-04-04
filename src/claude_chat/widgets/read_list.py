"""Connections list widget sorted by last message time."""

from __future__ import annotations

from textual import on
from textual.message import Message as TMessage
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option


class ReadList(Static):
    """Shows all connections with last message preview.

    tanmay_k -- hey check this out -- 2m ago
    dev_friend -- sounds good -- 1h ago

    Selecting an item posts ``OpenChat`` so the parent screen can push a
    ChatView.
    """

    DEFAULT_CSS = """
    ReadList {
        width: 100%;
        height: 100%;
    }

    ReadList #read-empty {
        width: 100%;
        height: auto;
        content-align: center middle;
        color: #888888;
        padding: 2;
    }

    ReadList OptionList {
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

    def compose(self):
        yield Static("No connections yet. Search for friends to get started!", id="read-empty")
        yield OptionList(id="read-option-list")

    def on_mount(self) -> None:
        self.query_one("#read-option-list", OptionList).display = False

    def update_data(
        self,
        connections: list,
        last_messages: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        """Refresh the connections list.

        ``connections`` is a list of User objects.
        ``last_messages`` maps user_id -> (plaintext_preview, relative_time).
        """
        option_list = self.query_one("#read-option-list", OptionList)
        empty_label = self.query_one("#read-empty", Static)

        option_list.clear_options()
        self._user_map: dict[int, tuple[str, str]] = {}

        if not connections:
            empty_label.display = True
            option_list.display = False
            return

        empty_label.display = False
        option_list.display = True

        last_messages = last_messages or {}

        for idx, user in enumerate(connections):
            preview, ago = last_messages.get(user.id, ("", ""))
            if preview:
                label = f"{user.claude_id} -- {preview[:40]} -- {ago}"
            else:
                label = f"{user.claude_id}"
            option_list.add_option(Option(label, id=str(idx)))
            self._user_map[idx] = (user.id, user.claude_id)

    @on(OptionList.OptionSelected, "#read-option-list")
    def _on_selected(self, event: OptionList.OptionSelected) -> None:
        idx = int(event.option.id)
        if idx in self._user_map:
            user_id, claude_id = self._user_map[idx]
            self.post_message(self.OpenChat(user_id, claude_id))
