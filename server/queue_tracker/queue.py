from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .database import Store


class QueueBridge:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.session: aiohttp.ClientSession | None = None
        self.socket: aiohttp.ClientWebSocketResponse | None = None
        self.task: asyncio.Task[None] | None = None
        self.previous: list[str] = []
        self.connected = False
        self._send_lock = asyncio.Lock()

    async def start(self) -> None:
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self._run(), name="mustardmine-queue")

    async def close(self) -> None:
        if self.task:
            self.task.cancel()
        if self.socket and not self.socket.closed:
            await self.socket.close()
        if self.session and not self.session.closed:
            await self.session.close()

    async def _run(self) -> None:
        delay = 2
        while True:
            try:
                settings = self.store.settings()
                if not self.session or self.session.closed:
                    self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))
                async with self.session.ws_connect(settings["queue_websocket_url"], heartbeat=25) as socket:
                    self.socket = socket
                    self.connected = True
                    delay = 2
                    await socket.send_json({"cmd": "init", "type": "chan_queue", "group": settings["queue_group"]})
                    async for message in socket:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            self._handle(json.loads(message.data))
                        elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Queue WebSocket disconnected")
            finally:
                self.connected = False
                self.socket = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    def _handle(self, payload: dict[str, Any]) -> None:
        if payload.get("cmd") != "update":
            return
        queue = payload.get("queue")
        if queue is None and isinstance(payload.get("data"), dict):
            queue = payload["data"].get("queue")
        if not isinstance(queue, list):
            return
        current = [str(item.get("title") or "") for item in queue if isinstance(item, dict) and item.get("title")]
        removed = self._first_slot_removed(self.previous, current)
        self.previous = current
        if removed:
            self.store.record_play(removed)

    @staticmethod
    def _first_slot_removed(previous: list[str], current: list[str]) -> str | None:
        if not previous or previous == current:
            return None
        if len(current) > len(previous) or previous[0] in current:
            return None
        if len(previous) == 1:
            return previous[0] if not current else None
        # A normal completion shifts every remaining song one place forward.
        overlap = min(len(previous) - 1, len(current))
        if overlap > 0 and previous[1:1 + overlap] == current[:overlap]:
            return previous[0]
        return None

    async def request(self, title: str, request_name: str) -> None:
        settings = self.store.settings()
        payload = {"cmd": settings["request_command"], "selection": title, "added_for": request_name}
        async with self._send_lock:
            if not self.socket or self.socket.closed:
                raise RuntimeError("The request queue is temporarily disconnected")
            await self.socket.send_json(payload)


async def hourly_maintenance(store: Store) -> None:
    while True:
        try:
            store.hourly_maintenance()
        except Exception:
            logging.exception("Hourly new-song maintenance failed")
        await asyncio.sleep(60 * 60)
