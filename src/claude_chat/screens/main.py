"""Main tabbed screen for claude-chat."""

from __future__ import annotations

from datetime import datetime, timezone

from textual import on, work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, TabbedContent, TabPane

from claude_chat.widgets.unread_list import UnreadList
from claude_chat.widgets.read_list import ReadList
from claude_chat.widgets.requests_panel import RequestsPanel
from claude_chat.widgets.search_panel import SearchPanel


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


class MainScreen(Screen):
    """Primary screen with Unread / Read / Requests / Search tabs."""

    CSS_PATH = []  # loaded via app CSS_PATH

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("escape", "back", "Back"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent("Unread", "Read", "Requests", "Search"):
            with TabPane("Unread", id="unread-tab"):
                yield UnreadList()
            with TabPane("Read", id="read-tab"):
                yield ReadList()
            with TabPane("Requests", id="requests-tab"):
                yield RequestsPanel()
            with TabPane("Search", id="search-tab"):
                yield SearchPanel()
        yield Footer()

    def on_mount(self) -> None:
        """Load initial data for all tabs."""
        self.load_data()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    @work(thread=True)
    def load_data(self) -> None:
        """Fetch data from Supabase in a worker thread."""
        client = self.app.client

        # Fetch unread messages grouped by sender
        try:
            unread_grouped = client.get_unread_messages()
        except Exception:
            unread_grouped = {}

        # Fetch connections
        try:
            connections = client.get_connections()
        except Exception:
            connections = []

        # Build last-message previews for each connection
        last_messages: dict[str, tuple[str, str]] = {}
        for user in connections:
            try:
                msgs = client.get_messages(user.id, limit=1)
                if msgs:
                    latest = msgs[0]
                    preview = (latest.plaintext or "")[:40]
                    ago = _relative_time(latest.created_at)
                    last_messages[user.id] = (preview, ago)
            except Exception:
                pass

        # Fetch requests
        try:
            incoming = client.get_incoming_requests()
        except Exception:
            incoming = []

        try:
            outgoing = client.get_outgoing_requests()
        except Exception:
            outgoing = []

        # Update widgets on the main thread
        self.app.call_from_thread(self._apply_data, unread_grouped, connections, last_messages, incoming, outgoing)

    def _apply_data(
        self,
        unread_grouped: dict,
        connections: list,
        last_messages: dict,
        incoming: list,
        outgoing: list,
    ) -> None:
        """Push fetched data into each widget (runs on main thread)."""
        try:
            self.query_one(UnreadList).update_data(unread_grouped)
        except Exception:
            pass

        try:
            self.query_one(ReadList).update_data(connections, last_messages)
        except Exception:
            pass

        try:
            self.query_one(RequestsPanel).update_data(incoming, outgoing)
        except Exception:
            pass

        try:
            self.query_one(SearchPanel).update_rate_limit(len(outgoing))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        """Reload all data."""
        self.notify("Refreshing...")
        self.load_data()

    def action_back(self) -> None:
        """Return to login screen."""
        self.app.pop_screen()

    # ------------------------------------------------------------------
    # Chat navigation — handle OpenChat from child widgets
    # ------------------------------------------------------------------

    @on(UnreadList.OpenChat)
    @on(ReadList.OpenChat)
    def _open_chat(self, event: UnreadList.OpenChat | ReadList.OpenChat) -> None:
        from claude_chat.screens.chat_view import ChatView

        self.app.push_screen(ChatView(event.user_id, event.claude_id))
