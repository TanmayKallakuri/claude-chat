"""Real-time message delivery via Pusher Channels.

Architecture:
- Publishing: Supabase Edge Function (push-notify) triggers Pusher events
  server-side. The Pusher secret never leaves the server.
- Subscribing: pysher client SDK connects to Pusher using the publishable
  key (no secret needed).
"""

import json
import logging
from typing import Callable

import pysher

from claude_chat.config import PUSHER_KEY, PUSHER_CLUSTER, SUPABASE_URL, SUPABASE_ANON_KEY

logger = logging.getLogger(__name__)


class RealtimeClient:
    """Handles real-time message and request delivery via Pusher.

    Each user has a channel: `user-{user_id}`
    Events: `new-message`, `new-request`
    """

    def __init__(self, user_id: str, auth_token: str | None = None):
        self._user_id = user_id
        self._auth_token = auth_token  # Supabase JWT for calling Edge Function
        self._message_callbacks: list[Callable] = []
        self._request_callbacks: list[Callable] = []
        self._connected = False
        self._channel = None

        # Client-side only — no Pusher secret needed
        self._client = pysher.Pusher(
            key=PUSHER_KEY,
            cluster=PUSHER_CLUSTER,
        )

    def connect(self) -> None:
        """Connect to Pusher and subscribe to user's channel."""
        self._client.connection.bind(
            "pusher:connection_established", self._on_connected
        )
        self._client.connection.bind(
            "pusher:connection_failed", self._on_failed
        )
        self._client.connect()

    def _on_connected(self, data: str) -> None:
        self._connected = True
        channel_name = f"user-{self._user_id}"
        self._channel = self._client.subscribe(channel_name)
        self._channel.bind("new-message", self._handle_message)
        self._channel.bind("new-request", self._handle_request)
        logger.info(f"Connected to Pusher, subscribed to {channel_name}")

    def _on_failed(self, data: str) -> None:
        self._connected = False
        logger.warning("Pusher connection failed")

    def disconnect(self) -> None:
        try:
            self._client.disconnect()
        except Exception:
            pass
        self._connected = False
        self._channel = None

    # ------------------------------------------------------------------
    # Publishing events via Supabase Edge Function (server-side)
    # ------------------------------------------------------------------

    def publish_message(self, receiver_id: str, message_data: dict) -> None:
        """Push a new-message event via the Edge Function."""
        self._call_edge_function(
            channel=f"user-{receiver_id}",
            event="new-message",
            data=message_data,
        )

    def publish_request(self, receiver_id: str, request_data: dict) -> None:
        """Push a new-request event via the Edge Function."""
        self._call_edge_function(
            channel=f"user-{receiver_id}",
            event="new-request",
            data=request_data,
        )

    def _call_edge_function(self, channel: str, event: str, data: dict) -> None:
        """Call the push-notify Edge Function to trigger a Pusher event."""
        import urllib.request
        import urllib.error

        url = f"{SUPABASE_URL}/functions/v1/push-notify"
        body = json.dumps({"channel": channel, "event": event, "data": data}).encode()

        headers = {
            "Content-Type": "application/json",
            "apikey": SUPABASE_ANON_KEY,
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception as exc:
            logger.warning(f"Edge function call failed: {exc}")

    # ------------------------------------------------------------------
    # Subscribing to events (from other users)
    # ------------------------------------------------------------------

    def on_message(self, callback: Callable[[dict], None]) -> None:
        self._message_callbacks.append(callback)

    def on_request(self, callback: Callable[[dict], None]) -> None:
        self._request_callbacks.append(callback)

    def _handle_message(self, data: str) -> None:
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return
        for cb in self._message_callbacks:
            try:
                cb(payload)
            except Exception as exc:
                logger.warning(f"Message callback error: {exc}")

    def _handle_request(self, data: str) -> None:
        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return
        for cb in self._request_callbacks:
            try:
                cb(payload)
            except Exception as exc:
                logger.warning(f"Request callback error: {exc}")

    @property
    def is_connected(self) -> bool:
        return self._connected
