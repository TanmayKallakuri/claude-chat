"""Real-time message delivery via Pusher Channels."""

import json
import logging
import threading
from typing import Callable

import pusher
import pysher

from claude_chat.config import (
    PUSHER_APP_ID,
    PUSHER_KEY,
    PUSHER_SECRET,
    PUSHER_CLUSTER,
)

logger = logging.getLogger(__name__)


class RealtimeClient:
    """Handles real-time message and request delivery via Pusher.

    Architecture:
    - Server SDK (`pusher`): triggers events on receiver's channel
    - Client SDK (`pysher`): subscribes to own channel for incoming events

    Each user has a channel: `user-{user_id}`
    Events: `new-message`, `new-request`
    """

    def __init__(self, user_id: str):
        self._user_id = user_id
        self._message_callbacks: list[Callable] = []
        self._request_callbacks: list[Callable] = []
        self._connected = False
        self._channel = None

        # Server-side client for triggering events
        self._server = pusher.Pusher(
            app_id=PUSHER_APP_ID,
            key=PUSHER_KEY,
            secret=PUSHER_SECRET,
            cluster=PUSHER_CLUSTER,
            ssl=True,
        )

        # Client-side for subscribing to events
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
        """Called when websocket connection is established."""
        self._connected = True
        channel_name = f"user-{self._user_id}"
        self._channel = self._client.subscribe(channel_name)
        self._channel.bind("new-message", self._handle_message)
        self._channel.bind("new-request", self._handle_request)
        logger.info(f"Connected to Pusher, subscribed to {channel_name}")

    def _on_failed(self, data: str) -> None:
        """Called when connection fails."""
        self._connected = False
        logger.warning("Pusher connection failed")

    def disconnect(self) -> None:
        """Disconnect from Pusher."""
        try:
            self._client.disconnect()
        except Exception:
            pass
        self._connected = False
        self._channel = None

    # ------------------------------------------------------------------
    # Publishing events (to other users)
    # ------------------------------------------------------------------

    def publish_message(self, receiver_id: str, message_data: dict) -> None:
        """Push a new-message event to the receiver's channel.

        message_data should contain: sender_id, sender_claude_id, message_id
        (NOT the encrypted content — the receiver fetches that from Supabase)
        """
        try:
            self._server.trigger(
                f"user-{receiver_id}",
                "new-message",
                message_data,
            )
        except Exception as exc:
            logger.warning(f"Failed to push message event: {exc}")

    def publish_request(self, receiver_id: str, request_data: dict) -> None:
        """Push a new-request event to the receiver's channel."""
        try:
            self._server.trigger(
                f"user-{receiver_id}",
                "new-request",
                request_data,
            )
        except Exception as exc:
            logger.warning(f"Failed to push request event: {exc}")

    # ------------------------------------------------------------------
    # Subscribing to events (from other users)
    # ------------------------------------------------------------------

    def on_message(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for incoming message events."""
        self._message_callbacks.append(callback)

    def on_request(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for incoming request events."""
        self._request_callbacks.append(callback)

    def _handle_message(self, data: str) -> None:
        """Internal handler for new-message events from Pusher."""
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
        """Internal handler for new-request events from Pusher."""
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
