"""Friend requests panel: incoming and outgoing."""

from __future__ import annotations

from datetime import datetime, timezone

from textual import on, work
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Label, Static


def _relative_time(dt: datetime | None) -> str:
    """Return a short human-readable relative time string."""
    if dt is None:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


class RequestsPanel(Widget):
    """Shows incoming and outgoing friend requests.

    Incoming requests have Accept / Reject buttons.
    Outgoing requests show pending status with time sent.
    """

    DEFAULT_CSS = """
    RequestsPanel {
        width: 100%;
        height: 100%;
    }
    RequestsPanel .section-header {
        color: #888888;
        padding: 1 1 0 1;
    }
    RequestsPanel .request-row {
        height: auto;
        padding: 0 1;
    }
    RequestsPanel .request-row Label {
        width: 1fr;
    }
    RequestsPanel .request-actions {
        height: auto;
        width: auto;
    }
    RequestsPanel #requests-empty {
        color: #666666;
        padding: 1;
    }
    RequestsPanel .outgoing-item {
        height: auto;
        padding: 0 1;
        color: #666666;
    }
    """

    def compose(self):
        with VerticalScroll():
            yield Static("Incoming", classes="section-header")
            yield Vertical(id="incoming-container")
            yield Static("Outgoing", classes="section-header")
            yield Vertical(id="outgoing-container")

    def update_data(
        self,
        incoming: list,
        outgoing: list,
    ) -> None:
        """Refresh both incoming and outgoing request lists.

        ``incoming`` and ``outgoing`` are lists of ConnectionRequest objects.
        """
        self._incoming = {req.id: req for req in incoming}
        self._outgoing = {req.id: req for req in outgoing}

        incoming_container = self.query_one("#incoming-container", Vertical)
        outgoing_container = self.query_one("#outgoing-container", Vertical)

        # Clear existing children
        incoming_container.remove_children()
        outgoing_container.remove_children()

        if not incoming:
            incoming_container.mount(
                Static("No pending requests.", id="requests-empty")
            )
        else:
            for req in incoming:
                name = req.sender_claude_id or req.sender_id[:8]
                row = Horizontal(classes="request-row")
                row.compose_add_child(Label(f"{name} wants to connect"))
                actions = Horizontal(classes="request-actions")
                accept_btn = Button(
                    "Accept", variant="success", id=f"accept-{req.id}"
                )
                reject_btn = Button(
                    "Reject", variant="error", id=f"reject-{req.id}"
                )
                actions.compose_add_child(accept_btn)
                actions.compose_add_child(reject_btn)
                row.compose_add_child(actions)
                incoming_container.mount(row)

        if not outgoing:
            outgoing_container.mount(
                Static("No outgoing requests", classes="outgoing-item")
            )
        else:
            for req in outgoing:
                name = req.receiver_claude_id or req.receiver_id[:8]
                ago = _relative_time(req.created_at)
                outgoing_container.mount(
                    Static(
                        f"Pending: {name} (sent {ago})",
                        classes="outgoing-item",
                    )
                )

    @on(Button.Pressed)
    def _on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("accept-"):
            request_id = button_id[len("accept-"):]
            self._respond(request_id, accept=True)
        elif button_id.startswith("reject-"):
            request_id = button_id[len("reject-"):]
            self._respond(request_id, accept=False)

    @work(thread=True)
    def _respond(self, request_id: str, accept: bool) -> None:
        """Accept or reject a request in a worker thread."""
        client = self.app.client
        try:
            client.respond_to_request(request_id, accept)
        except Exception as exc:
            self.app.call_from_thread(
                self.notify, f"Error: {exc}", severity="error"
            )
            return

        action = "Accepted" if accept else "Rejected"
        self.app.call_from_thread(
            self.notify, f"{action} request", severity="information"
        )

        # Refresh the parent screen data
        self.app.call_from_thread(self._request_refresh)

    def _request_refresh(self) -> None:
        """Ask the main screen to reload data."""
        from claude_chat.screens.main import MainScreen

        screen = self.screen
        if isinstance(screen, MainScreen):
            screen.load_data()
