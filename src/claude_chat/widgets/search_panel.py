"""User search and friend request panel."""

from __future__ import annotations

from textual import on, work
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static


class SearchPanel(Widget):
    """Search for users and send friend requests.

    Contains a search input, results list with Send Request buttons,
    and a rate limit indicator.
    """

    DEFAULT_CSS = """
    SearchPanel {
        width: 100%;
        height: 100%;
    }
    SearchPanel #search-results {
        width: 100%;
        height: 1fr;
    }
    SearchPanel .result-row {
        height: auto;
        padding: 0 1;
    }
    SearchPanel .result-row Label {
        width: 1fr;
    }
    SearchPanel #search-status {
        color: #666666;
        padding: 0 1;
    }
    SearchPanel #rate-limit {
        color: #666666;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._requests_sent_today: int = 0

    def compose(self):
        yield Input(placeholder="Search by claude_id...", id="search-input")
        yield Static("", id="search-status")
        yield VerticalScroll(id="search-results")
        yield Static("", id="rate-limit")

    def update_rate_limit(self, count: int) -> None:
        """Update the displayed request count."""
        self._requests_sent_today = count
        self.query_one("#rate-limit", Static).update(
            f"Requests today: {count}/3"
        )

    @on(Input.Submitted, "#search-input")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        self._set_status("Searching...")
        self._do_search(query)

    def _set_status(self, text: str) -> None:
        self.query_one("#search-status", Static).update(text)

    @work(thread=True)
    def _do_search(self, query: str) -> None:
        """Run user search in worker thread."""
        client = self.app.client
        try:
            users = client.search_users(query)
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Error: {exc}")
            return

        self.app.call_from_thread(self._show_results, users)

    def _show_results(self, users: list) -> None:
        """Populate results in the search results container."""
        results_container = self.query_one("#search-results", VerticalScroll)
        results_container.remove_children()
        self._result_map: dict[str, object] = {}

        if not users:
            self._set_status("No users found")
            return

        self._set_status(f"Found {len(users)} user(s)")

        for user in users:
            self._result_map[user.id] = user
            row = Horizontal(classes="result-row")
            row.compose_add_child(Label(user.claude_id))
            btn = Button(
                "Send Request",
                variant="success",
                id=f"send-req-{user.id}",
            )
            row.compose_add_child(btn)
            results_container.mount(row)

    @on(Button.Pressed)
    def _on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("send-req-"):
            target_id = button_id[len("send-req-"):]
            event.button.disabled = True
            event.button.label = "Sending..."
            self._send_request(target_id, event.button)

    @work(thread=True)
    def _send_request(self, target_id: str, button: Button) -> None:
        """Send a friend request in a worker thread."""
        client = self.app.client
        try:
            client.send_request(target_id)
        except ValueError as exc:
            self.app.call_from_thread(
                self.notify, str(exc), severity="error"
            )
            self.app.call_from_thread(self._reset_button, button)
            return
        except Exception as exc:
            self.app.call_from_thread(
                self.notify, f"Error: {exc}", severity="error"
            )
            self.app.call_from_thread(self._reset_button, button)
            return

        self._requests_sent_today += 1
        self.app.call_from_thread(
            self.notify, "Request sent!", severity="information"
        )
        self.app.call_from_thread(self._mark_sent, button)
        self.app.call_from_thread(
            self.update_rate_limit, self._requests_sent_today
        )

    def _reset_button(self, button: Button) -> None:
        button.disabled = False
        button.label = "Send Request"

    def _mark_sent(self, button: Button) -> None:
        button.label = "Sent"
        button.disabled = True
