from __future__ import annotations

import asyncio
import json
import logging
import os
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
        self.current_queue: list[dict[str, str]] = []
        self.connected = False
        self._send_lock = asyncio.Lock()
        self._choose_reply: asyncio.Future[dict[str, Any]] | None = None
        self._choose_expected: tuple[str, str, int] | None = None
        self.auth_cookie = os.getenv("MUSTARDMINE_COOKIE", "").strip()

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
                headers = {"Cookie": self.auth_cookie} if self.auth_cookie else None
                async with self.session.ws_connect(settings["queue_websocket_url"], heartbeat=25, headers=headers) as socket:
                    self.socket = socket
                    self.connected = True
                    delay = 2
                    logging.info("Queue WebSocket connected (request authentication configured: %s)", bool(self.auth_cookie))
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
                if self._choose_reply and not self._choose_reply.done():
                    self._choose_reply.set_exception(RuntimeError("The request queue disconnected before confirming the request"))
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    def _handle(self, payload: dict[str, Any]) -> None:
        if payload.get("cmd") == "choose":
            if payload.get("error"):
                logging.warning("MustardMine rejected a queue request: %s", payload["error"])
            if self._choose_reply and not self._choose_reply.done():
                self._choose_reply.set_result(payload)
            return
        if payload.get("cmd") != "update":
            return
        queue = payload.get("queue")
        if queue is None and isinstance(payload.get("data"), dict):
            queue = payload["data"].get("queue")
        if not isinstance(queue, list):
            return
        self.current_queue = [
            {"title": str(item.get("title") or ""), "user": str(item.get("user") or "")}
            for item in queue
            if isinstance(item, dict) and item.get("title")
        ]
        if self._choose_reply and not self._choose_reply.done() and self._choose_expected:
            title, request_name, previous_count = self._choose_expected
            current_count = sum(item["title"] == title and item["user"] == request_name for item in self.current_queue)
            if current_count > previous_count:
                self._choose_reply.set_result({"cmd": "choose", "selection": title, "confirmed_by": "queue_update"})
        current = [item["title"] for item in self.current_queue]
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
        if not self.auth_cookie:
            raise RuntimeError("Song requests are not configured on the server")
        payload = {"cmd": "choose", "selection": title, "added_for": request_name}
        async with self._send_lock:
            if not self.socket or self.socket.closed:
                raise RuntimeError("The request queue is temporarily disconnected")
            reply = asyncio.get_running_loop().create_future()
            self._choose_reply = reply
            previous_count = sum(item["title"] == title and item["user"] == request_name for item in self.current_queue)
            self._choose_expected = (title, request_name, previous_count)
            try:
                logging.info("Sending MustardMine queue request for %r on behalf of %r", title, request_name)
                await self.socket.send_json(payload)
                result = await asyncio.wait_for(reply, timeout=10)
            except TimeoutError as error:
                logging.warning("MustardMine did not confirm the queue request for %r", title)
                raise RuntimeError("The request queue did not confirm the request") from error
            finally:
                if self._choose_reply is reply:
                    self._choose_reply = None
                    self._choose_expected = None
            if result.get("error"):
                raise RuntimeError(str(result["error"]))
            logging.info("MustardMine confirmed the queue request for %r", result.get("selection") or title)


async def hourly_maintenance(store: Store) -> None:
    while True:
        try:
            store.hourly_maintenance()
        except Exception:
            logging.exception("Hourly new-song maintenance failed")
        await asyncio.sleep(60 * 60)
