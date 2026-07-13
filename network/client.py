"""
network/client.py
=================
King's Trial — NetworkClient

Wraps a WebSocket connection in a background asyncio thread so the
Pygame main loop never blocks waiting for network I/O.

Thread model
------------
  Main thread  (Pygame)   ←→  queue.Queue  ←→  Daemon thread  (asyncio loop)

Usage
-----
    client = NetworkClient()
    client.connect("ws://localhost:8765", "ABC123", "host", token="<uuid>")

    # each Pygame frame:
    for msg in client.poll():
        handle(msg)

    # to send:
    client.send({"type": "move", "room": "ABC123", "from": [4,5], "to": [5,5]})

    # on exit:
    client.disconnect()
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import uuid
from typing import Optional

log = logging.getLogger("KingsTrial.network")


class NetworkClient:
    """
    Thread-safe WebSocket client.

    All WebSocket I/O runs in a background daemon thread.
    The Pygame thread communicates via two queue.Queue objects.
    """

    # Connection statuses exposed to the UI
    STATUS_CONNECTING    = "connecting"
    STATUS_CONNECTED     = "connected"
    STATUS_RECONNECTING  = "reconnecting"
    STATUS_DISCONNECTED  = "disconnected"
    STATUS_ERROR         = "error"

    def __init__(self) -> None:
        self._inbound:  queue.Queue = queue.Queue()
        self._outbound: queue.Queue = queue.Queue()

        self._status:  str = self.STATUS_DISCONNECTED
        self._error:   str = ""

        # Set by connect()
        self._url:          str  = ""
        self._room_code:    str  = ""
        self._role:         str  = ""   # "host" | "joiner"
        self._token:        str  = ""

        # Background thread / event loop
        self._loop:   Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread]          = None
        self._stop_event: Optional[asyncio.Event]         = None

    # ------------------------------------------------------------------
    # Public API (called from the Pygame/main thread)
    # ------------------------------------------------------------------

    def connect(
        self,
        url:        str,
        room_code:  str,
        role:       str,               # "host" | "joiner"
        token:      str | None = None,
    ) -> None:
        """
        Start the background connection.
        Safe to call multiple times (disconnects first if already running).
        """
        self.disconnect()

        self._url       = url
        self._room_code = room_code.upper().strip()
        self._role      = role
        self._token     = token or str(uuid.uuid4())
        self._status    = self.STATUS_CONNECTING
        self._error     = ""

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="NetworkClient",
        )
        self._thread.start()
        log.info("NetworkClient: connecting as %s to room %s @ %s",
                 role, room_code, url)

    def send(self, msg: dict) -> None:
        """Queue a message for sending (thread-safe, non-blocking)."""
        self._outbound.put(msg)

    def poll(self) -> list[dict]:
        """
        Drain all waiting inbound messages.
        Call once per Pygame frame.  Returns a list (possibly empty).
        """
        msgs = []
        while True:
            try:
                msgs.append(self._inbound.get_nowait())
            except queue.Empty:
                break
        return msgs

    def disconnect(self) -> None:
        """Signal the background thread to stop and wait briefly."""
        if self._loop and self._loop.is_running():
            if self._stop_event:
                self._loop.call_soon_threadsafe(self._stop_event.set)
        self._status = self.STATUS_DISCONNECTED

    @property
    def status(self) -> str:
        return self._status

    @property
    def room_code(self) -> str:
        return self._room_code

    @property
    def token(self) -> str:
        return self._token

    @property
    def error(self) -> str:
        return self._error

    # ------------------------------------------------------------------
    # Background thread internals
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Entry point for the daemon thread. Runs the asyncio event loop."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:
            log.error("NetworkClient loop error: %s", exc)
            self._status = self.STATUS_ERROR
            self._error  = str(exc)
        finally:
            self._loop.close()

    async def _main(self) -> None:
        """Top-level async task: connect (with retries) and run IO."""
        self._stop_event = asyncio.Event()

        backoff = 1.0
        max_backoff = 30.0
        attempt = 0

        while not self._stop_event.is_set():
            try:
                attempt += 1
                if attempt > 1:
                    self._status = self.STATUS_RECONNECTING
                    log.info("NetworkClient: reconnect attempt %d (backoff %.1fs)",
                             attempt, backoff)
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=backoff,
                        )
                        break   # stop_event fired during backoff
                    except asyncio.TimeoutError:
                        pass
                    backoff = min(backoff * 2, max_backoff)

                async with self._open_connection() as ws:
                    self._status = self.STATUS_CONNECTED
                    backoff = 1.0   # reset on successful connect
                    log.info("NetworkClient: connected")

                    # Send the initial room message
                    await self._send_initial(ws)

                    # Run sender + receiver concurrently
                    await asyncio.gather(
                        self._receiver(ws),
                        self._sender(ws),
                        self._stop_watcher(ws),
                    )

            except Exception as exc:
                if self._stop_event.is_set():
                    break
                log.warning("NetworkClient: connection lost (%s)", exc)
                self._status = self.STATUS_RECONNECTING

        log.info("NetworkClient: stopped")
        self._status = self.STATUS_DISCONNECTED

    def _open_connection(self):
        """Return an async context manager for a WebSocket connection."""
        import websockets
        return websockets.connect(self._url)

    async def _send_initial(self, ws) -> None:
        """Send the create_room / join_room / reconnect handshake."""
        if self._role == "host":
            msg = {
                "type":  "create_room",
                "room":  self._room_code,
                "token": self._token,
            }
        else:
            msg = {
                "type":  "join_room",
                "room":  self._room_code,
                "token": self._token,
            }
        await ws.send(json.dumps(msg))

    async def _receiver(self, ws) -> None:
        """Receive loop — puts incoming messages on the inbound queue."""
        async for raw in ws:
            try:
                data = json.loads(raw)
                self._inbound.put(data)
            except json.JSONDecodeError as exc:
                log.warning("NetworkClient: bad JSON: %s", exc)

    async def _sender(self, ws) -> None:
        """Send loop — drains the outbound queue and sends to relay."""
        while True:
            try:
                msg = self._outbound.get_nowait()
                await ws.send(json.dumps(msg))
            except queue.Empty:
                await asyncio.sleep(0.03)
            except Exception:
                return   # connection closed; outer loop will reconnect

    async def _stop_watcher(self, ws) -> None:
        """Cancel the connection when disconnect() is called."""
        await self._stop_event.wait()
        await ws.close()


# ---------------------------------------------------------------------------
# Reconnect variant (same client, different initial message)
# ---------------------------------------------------------------------------

class ReconnectClient(NetworkClient):
    """
    Subclass that sends a 'reconnect' message on connect instead of
    create_room / join_room.  Used when a player re-joins an existing room.
    """

    async def _send_initial(self, ws) -> None:
        msg = {
            "type":  "reconnect",
            "room":  self._room_code,
            "token": self._token,
        }
        await ws.send(json.dumps(msg))
