"""Main tabbed screen for claude-chat."""

from __future__ import annotations

from datetime import datetime, timezone

from textual import on, work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Tab, TabbedContent, TabPane

from claude_chat.widgets.unread_list import UnreadList
from claude_chat.widgets.read_list import ReadList
from claude_chat.widgets.requests_panel import RequestsPanel
from claude_chat.widgets.search_panel import SearchPanel
from claude_chat.notifications import play_chime


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
        """Load initial data for all tabs and start real-time subscriptions."""
        self._unread_count = 0
        self.load_data()
        self._start_realtime()
        # Polling fallback every 10 seconds in case realtime drops
        self._poll_timer = self.set_interval(10, self.load_data)

    def on_unmount(self) -> None:
        """Clean up timer and subscriptions."""
        if hasattr(self, '_poll_timer') and self._poll_timer:
            self._poll_timer.stop()
        # Clean up realtime subscriptions
        client = getattr(self.app, 'client', None)
        if client and hasattr(client, 'unsubscribe_all'):
            try:
                client.unsubscribe_all()
            except Exception:
                pass

    def on_screen_resume(self) -> None:
        """Refresh data when returning from ChatView."""
        self.load_data()

    # ------------------------------------------------------------------
    # Realtime subscriptions
    # ------------------------------------------------------------------

    @work(thread=True)
    def _start_realtime(self) -> None:
        """Subscribe to incoming messages and friend requests via Supabase Realtime."""
        client = self.app.client
        try:
            client.subscribe_messages(self._on_realtime_message)
        except Exception:
            pass
        try:
            client.subscribe_requests(self._on_realtime_request)
        except Exception:
            pass

    def _on_realtime_message(self, msg) -> None:
        """Callback fired by Supabase Realtime on new incoming message."""
        play_chime("message")
        # Check if ChatView for this sender is currently on screen
        self.app.call_from_thread(self._handle_realtime_message, msg)

    def _handle_realtime_message(self, msg) -> None:
        """Process an incoming realtime message on the main thread."""
        from claude_chat.screens.chat_view import ChatView

        try:
            current = self.app.screen
            if isinstance(current, ChatView) and current.other_user_id == msg.sender_id:
                current.append_realtime_message(msg)
                return
        except Exception:
            pass
        self.load_data()

    def _on_realtime_request(self, req) -> None:
        """Callback fired by Supabase Realtime on new friend request."""
        play_chime("request")
        self.app.call_from_thread(self.load_data)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    @work(thread=True, exclusive=True)
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

        # Update the Unread tab label with the count
        total_unread = sum(len(msgs) for msgs in unread_grouped.values())
        self._unread_count = total_unread
        self._update_unread_tab_label(total_unread)

    def _update_unread_tab_label(self, count: int) -> None:
        """Set the Unread tab title to include the count when > 0."""
        try:
            tab_pane = self.query_one("#unread-tab", TabPane)
            # Textual TabPane stores label; find the matching Tab widget
            tabs = self.query(Tab)
            for tab in tabs:
                if tab.id == "--content-tab-unread-tab":
                    tab.label = f"Unread ({count})" if count > 0 else "Unread"
                    break
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
        """Quit the application."""
        self.app.exit()

    # ------------------------------------------------------------------
    # Chat navigation — handle OpenChat from child widgets
    # ------------------------------------------------------------------

    @on(UnreadList.OpenChat)
    @on(ReadList.OpenChat)
    def _open_chat(self, event: UnreadList.OpenChat | ReadList.OpenChat) -> None:
        from claude_chat.screens.chat_view import ChatView

        self.app.push_screen(ChatView(event.user_id, event.claude_id))
