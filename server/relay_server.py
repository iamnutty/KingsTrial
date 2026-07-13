"""
server/relay_server.py
======================
King's Trial — WebSocket relay server.

Acts as a simple message broker between two players.
Rooms are created by Hosts and joined by Joiners.
All game logic stays on the clients — the server only
forwards messages and manages room lifecycle.

Environment variables:
    PORT  — TCP port to listen on (default: 8080, Fly.io sets this automatically)
    HOST  — bind address (default: 0.0.0.0)

Run locally:
    python relay_server.py

Deploy (Fly.io):
    fly deploy --app kings-trial-server

Health check:
    GET /  →  200 OK  {"status":"ok","rooms":<count>}
    Fly.io requires this endpoint to confirm the server is alive.
"""

import asyncio
import json
import logging
import os
import time
import uuid

import websockets
from websockets.exceptions import ConnectionClosed

logging.basicConfig(
    level=logging.INFO,
    format="[relay] %(asctime)s %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("relay")

# ---------------------------------------------------------------------------
# Room registry
# ---------------------------------------------------------------------------
# room_code (str) → room dict:
#   host_ws       : WebSocket | None
#   joiner_ws     : WebSocket | None
#   host_token    : str
#   joiner_token  : str | None
#   session_config: dict | None   (layout, time_control, neutral_ai from host)
#   host_ready    : bool
#   joiner_ready  : bool
#   created_at    : float (unix timestamp)
#   started       : bool
rooms: dict[str, dict] = {}

# Reverse lookup: websocket → (room_code, role)
ws_room: dict = {}   # websocket → (room_code, "host"|"joiner")

# How long (seconds) to keep a room after the last player disconnects
ROOM_TTL = 7200        # 2 hours
RECONNECT_WINDOW = 60  # seconds


def _make_room(room_code: str, host_token: str) -> dict:
    return {
        "host_ws":       None,
        "joiner_ws":     None,
        "host_token":    host_token,
        "joiner_token":  None,
        "session_config": None,
        "host_color":    "white",
        "host_ready":    False,
        "joiner_ready":  False,
        "created_at":    time.time(),
        "started":       False,
    }


async def _send(ws, msg: dict) -> None:
    """Send a JSON message, ignoring closed-connection errors."""
    try:
        await ws.send(json.dumps(msg))
    except Exception:
        pass


async def _forward(sender_ws, msg: dict) -> None:
    """Forward msg to the OTHER player in the room."""
    entry = ws_room.get(sender_ws)
    if not entry:
        return
    room_code, role = entry
    room = rooms.get(room_code)
    if not room:
        return

    target_ws = room["joiner_ws"] if role == "host" else room["host_ws"]
    if target_ws:
        await _send(target_ws, msg)


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def handle(websocket) -> None:
    log.info("New connection from %s", websocket.remote_address)
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {"type": "error", "msg": "Invalid JSON"})
                continue

            mtype = msg.get("type", "")
            await _dispatch(websocket, mtype, msg)

    except ConnectionClosed:
        pass
    finally:
        await _on_disconnect(websocket)


async def _dispatch(ws, mtype: str, msg: dict) -> None:
    """Route an incoming message to the appropriate handler."""

    if mtype == "create_room":
        await _handle_create_room(ws, msg)

    elif mtype == "join_room":
        await _handle_join_room(ws, msg)

    elif mtype == "reconnect":
        await _handle_reconnect(ws, msg)

    elif mtype in ("color_choice", "player_ready", "move", "promote",
                   "respawn", "phase_sync", "state_snapshot", "chat"):
        # Game messages — forward to the other player
        # Intercept player_ready to track ready state on the server
        if mtype == "player_ready":
            await _handle_player_ready(ws, msg)
        elif mtype == "color_choice":
            # Store session_config and host_color sent by host alongside color choice
            entry = ws_room.get(ws)
            if entry:
                room = rooms.get(entry[0])
                if room:
                    if msg.get("session_config"):
                        room["session_config"] = msg["session_config"]
                    if msg.get("host_color"):
                        room["host_color"] = msg["host_color"]
            await _forward(ws, msg)
        else:
            await _forward(ws, msg)

    else:
        log.warning("Unknown message type: %s", mtype)


# ---------------------------------------------------------------------------
# Specific handlers
# ---------------------------------------------------------------------------

async def _handle_create_room(ws, msg: dict) -> None:
    room_code = msg.get("room", "").upper().strip()
    token = msg.get("token") or str(uuid.uuid4())

    if not room_code:
        await _send(ws, {"type": "error", "msg": "room code required"})
        return

    if room_code in rooms:
        await _send(ws, {"type": "error", "msg": "Room already exists"})
        return

    room = _make_room(room_code, token)
    room["host_ws"] = ws
    rooms[room_code] = room
    ws_room[ws] = (room_code, "host")

    log.info("Room created: %s", room_code)
    await _send(ws, {
        "type":  "room_created",
        "room":  room_code,
        "token": token,
    })


async def _handle_join_room(ws, msg: dict) -> None:
    room_code = msg.get("room", "").upper().strip()
    token = msg.get("token") or str(uuid.uuid4())

    room = rooms.get(room_code)
    if not room:
        await _send(ws, {"type": "error", "msg": "Room not found"})
        return

    if room["joiner_ws"] is not None:
        await _send(ws, {"type": "error", "msg": "Room is full"})
        return

    room["joiner_ws"] = ws
    room["joiner_token"] = token
    ws_room[ws] = (room_code, "joiner")

    log.info("Room joined: %s", room_code)

    # Confirm to joiner
    await _send(ws, {
        "type":  "room_joined",
        "room":  room_code,
        "token": token,
    })

    # Notify host that opponent arrived
    if room["host_ws"]:
        await _send(room["host_ws"], {"type": "opponent_joined"})


async def _handle_reconnect(ws, msg: dict) -> None:
    room_code = msg.get("room", "").upper().strip()
    token = msg.get("token", "")

    room = rooms.get(room_code)
    if not room:
        await _send(ws, {"type": "error", "msg": "Room expired or not found"})
        return

    if token == room["host_token"]:
        role = "host"
        room["host_ws"] = ws
        peer_ws = room["joiner_ws"]
    elif token == room["joiner_token"]:
        role = "joiner"
        room["joiner_ws"] = ws
        peer_ws = room["host_ws"]
    else:
        await _send(ws, {"type": "error", "msg": "Invalid session token"})
        return

    ws_room[ws] = (room_code, role)
    log.info("Reconnected: %s as %s", room_code, role)

    await _send(ws, {"type": "reconnected", "role": role, "room": room_code})
    if peer_ws:
        await _send(peer_ws, {"type": "opponent_reconnected"})


async def _handle_player_ready(ws, msg: dict) -> None:
    entry = ws_room.get(ws)
    if not entry:
        return
    room_code, role = entry
    room = rooms.get(room_code)
    if not room:
        return

    if role == "host":
        room["host_ready"] = True
        if msg.get("host_color"):
            room["host_color"] = msg["host_color"]
    else:
        room["joiner_ready"] = True

    # Forward the ready signal to the peer
    await _forward(ws, msg)

    # If both are ready, broadcast start_game
    if room["host_ready"] and room["joiner_ready"] and not room["started"]:
        room["started"] = True
        host_color = room.get("host_color", "white")  # Read cached host_color from room state
        start_msg = {
            "type":           "start_game",
            "white_role":     "host" if host_color == "white" else "joiner",
            "session_config": room.get("session_config", {}),
        }
        log.info("Starting game in room %s  white=%s", room_code, start_msg["white_role"])
        for target_ws in (room["host_ws"], room["joiner_ws"]):
            if target_ws:
                await _send(target_ws, start_msg)


# ---------------------------------------------------------------------------
# Disconnect handling
# ---------------------------------------------------------------------------

async def _on_disconnect(ws) -> None:
    entry = ws_room.pop(ws, None)
    if not entry:
        return

    room_code, role = entry
    room = rooms.get(room_code)
    if not room:
        return

    log.info("Disconnected: %s from room %s", role, room_code)

    if role == "host":
        room["host_ws"] = None
        peer_ws = room["joiner_ws"]
    else:
        room["joiner_ws"] = None
        peer_ws = room["host_ws"]

    if peer_ws:
        await _send(peer_ws, {
            "type":                "opponent_disconnected",
            "role":                role,
            "reconnect_window_sec": RECONNECT_WINDOW,
        })

    # Schedule room cleanup if both players gone
    asyncio.get_event_loop().call_later(
        RECONNECT_WINDOW + 5,
        lambda: _cleanup_room(room_code),
    )


def _cleanup_room(room_code: str) -> None:
    room = rooms.get(room_code)
    if not room:
        return
    # Only remove if both slots are empty
    if room["host_ws"] is None and room["joiner_ws"] is None:
        rooms.pop(room_code, None)
        log.info("Room %s removed (both players gone)", room_code)


# ---------------------------------------------------------------------------
# Periodic stale-room sweep
# ---------------------------------------------------------------------------

async def _sweep_stale_rooms() -> None:
    """Remove rooms older than ROOM_TTL with no active connections."""
    while True:
        await asyncio.sleep(600)  # run every 10 minutes
        now = time.time()
        to_delete = [
            code for code, r in list(rooms.items())
            if now - r["created_at"] > ROOM_TTL
            and r["host_ws"] is None
            and r["joiner_ws"] is None
        ]
        for code in to_delete:
            rooms.pop(code, None)
            log.info("Stale room %s swept", code)




# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    host      = os.environ.get("HOST", "0.0.0.0")
    ws_port   = int(os.environ.get("PORT", 8080))

    # Fly.io sends all traffic (HTTP + WS upgrade) to the same port.
    # We run the health-check HTTP server on the same port by letting the
    # WebSocket library handle the upgrade internally — but websockets.serve
    # only speaks WS.  Solution: run a *separate* HTTP server on a different
    # port and use Fly.io's process_groups, OR — simpler — handle the health
    # check inside the WS server's process_request hook.
    #
    # We use the process_request hook approach: any plain HTTP GET / that
    # does NOT contain an Upgrade header is answered inline.
    # This keeps everything on a single port with zero extra threads.

    log.info("King's Trial relay server starting on %s:%d", host, ws_port)

    asyncio.get_event_loop().create_task(_sweep_stale_rooms())

    async with websockets.serve(
        handle,
        host,
        ws_port,
        process_request=_http_health_check,
    ):
        log.info("Relay ready — waiting for connections (port %d)", ws_port)
        await asyncio.Future()   # run forever


async def _http_health_check(connection, request):
    """
    websockets >= 14 process_request hook.

    The new asyncio API passes (connection, request) where request is a
    websockets.http11.Request object — NOT a plain headers dict.

    Plain HTTP requests (no Upgrade: websocket header) are answered with a
    JSON health-check response so Fly.io knows the server is alive.
    WebSocket upgrade requests return None and are handled normally.
    """
    from websockets.http11 import Response
    from websockets.datastructures import Headers

    upgrade = request.headers.get("Upgrade", "").lower()
    if upgrade != "websocket":
        body = json.dumps({"status": "ok", "rooms": len(rooms)}).encode()
        return Response(
            status_code=200,
            reason_phrase="OK",
            headers=Headers([
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
                ("Connection", "close"),
            ]),
            body=body,
        )
    # WebSocket upgrade — let the library handle it normally
    return None


if __name__ == "__main__":
    asyncio.run(main())
