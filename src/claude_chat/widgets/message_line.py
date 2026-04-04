"""Single chat message widget."""

from __future__ import annotations

from textual.widgets import Static


class MessageLine(Static):
    """Renders a single message in CLI style.

    [14:32] tanmay_k: hey, check out this PR
    [14:33] you: looks good, merging now
    """

    DEFAULT_CSS = """
    MessageLine {
        width: 100%;
        height: auto;
        padding: 0 1;
    }
    """

    def __init__(
        self,
        timestamp: str,
        sender: str,
        text: str,
        is_self: bool = False,
        **kwargs,
    ) -> None:
        self.timestamp = timestamp
        self.sender = sender
        self.text = text
        self.is_self = is_self
        super().__init__(**kwargs)

    def render(self) -> str:
        name = "you" if self.is_self else self.sender
        style = "bold #4ecca3" if self.is_self else "bold"
        return f"[dim][{self.timestamp}][/dim] [{style}]{name}[/{style}]: {self.text}"
