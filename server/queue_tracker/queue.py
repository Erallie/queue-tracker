from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .database import Store


class SongAlreadyQueuedError(RuntimeError):
    pass


class QueueLimitError(RuntimeError):
    pass


class QueueClosedError(RuntimeError):
    pass


class QueueBridge:
    """The authoritative, persistent queue hosted by this service."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.current_queue: list[dict[str, Any]] = []
        self.queue_open = bool(store.settings()["queue_open"])
        self.close_after = max(0, int(store.settings()["queue_close_after"]))
        self.listeners: set[asyncio.Queue[list[dict[str, Any]]]] = set()
        self.connected = True
        self._lock = asyncio.Lock()
        self.on_request_added: Callable[[str, str], None] | None = None
        self.on_open_changed: Callable[[bool], None] | None = None

    async def start(self) -> None:
        self.refresh()

    async def close(self) -> None:
        return

    def refresh(self) -> None:
        self.current_queue = self.store.queue_entries()
        settings = self.store.settings()
        self.queue_open = bool(settings["queue_open"])
        self.close_after = max(0, int(settings["queue_close_after"]))
        self._publish_queue()

    def subscribe(self) -> asyncio.Queue[list[dict[str, Any]]]:
        listener: asyncio.Queue[list[dict[str, Any]]] = asyncio.Queue(maxsize=1)
        listener.put_nowait(list(self.current_queue))
        self.listeners.add(listener)
        return listener

    def unsubscribe(self, listener: asyncio.Queue[list[dict[str, Any]]]) -> None:
        self.listeners.discard(listener)

    def _publish_queue(self) -> None:
        snapshot = list(self.current_queue)
        for listener in self.listeners:
            if listener.full():
                listener.get_nowait()
            listener.put_nowait(snapshot)

    async def set_open(self, open_: bool, close_after: int = 0) -> None:
        async with self._lock:
            self.refresh()
            was_open = self.queue_open
            self.store.set_queue_state(open_, close_after)
            self.refresh()
        self._notify_open_change(was_open)
        if close_after:
            logging.info("Request queue will close after %d more request(s)", close_after)
        else:
            logging.info("Request queue is now %s", "open" if open_ else "closed")

    async def request(
        self,
        title: str,
        request_name: str,
        grouped_titles: list[str] | None = None,
        *,
        user_id: str | None = None,
        requester_provider: str = "",
        requester_provider_id: str = "",
    ) -> None:
        async with self._lock:
            self.refresh()
            was_open = self.queue_open
            if not self.queue_open:
                raise QueueClosedError("The request queue is closed")
            queued = {self._queue_title_key(item["title"]) for item in self.current_queue}
            requested_titles = {title, *(grouped_titles or [])}
            if any(self._queue_title_key(requested_title) in queued for requested_title in requested_titles):
                raise SongAlreadyQueuedError("Song is already in the queue!")
            limit = max(0, int(self.store.settings()["queue_limit_per_person"]))
            if limit and sum(
                self._same_requester(
                    item,
                    request_name,
                    user_id,
                    requester_provider,
                    requester_provider_id,
                )
                for item in self.current_queue
            ) >= limit:
                raise QueueLimitError("You already have requests pending.")
            self.store.enqueue(
                title,
                request_name,
                user_id=user_id,
                requester_provider=requester_provider,
                requester_provider_id=requester_provider_id,
            )
            self.store.consume_queue_slot()
            self.refresh()
        self._notify_request_added(title, request_name)
        self._notify_open_change(was_open)
        logging.info("Queued %r on behalf of %r", title, request_name)

    async def remove(self, index: int, expected_title: str, expected_user: str) -> None:
        async with self._lock:
            self.refresh()
            was_open = self.queue_open
            if index < 0 or index >= len(self.current_queue):
                raise RuntimeError("That request is no longer in the queue")
            current = self.current_queue[index]
            if current["title"] != expected_title or current["user"] != expected_user:
                raise RuntimeError("The request queue changed; please try again")
            self.store.remove_queue_entry(str(current["id"]))
            self.store.restore_queue_slot()
            self.refresh()
        self._notify_open_change(was_open)

    async def remove_by_id(self, entry_id: str) -> dict[str, Any] | None:
        async with self._lock:
            self.refresh()
            was_open = self.queue_open
            removed = self.store.remove_queue_entry(entry_id)
            if removed:
                self.store.restore_queue_slot()
            self.refresh()
        self._notify_open_change(was_open)
        return removed

    def _notify_request_added(self, title: str, request_name: str) -> None:
        if self.on_request_added:
            try:
                self.on_request_added(title, request_name)
            except Exception:
                logging.exception("Could not schedule Twitch request announcement")

    def _notify_open_change(self, was_open: bool) -> None:
        if was_open == self.queue_open or not self.on_open_changed:
            return
        try:
            self.on_open_changed(self.queue_open)
        except Exception:
            logging.exception("Could not schedule Twitch queue-status announcement")

    async def complete(self, entry_id: str) -> dict[str, Any] | None:
        async with self._lock:
            removed = self.store.remove_queue_entry(entry_id)
            if removed:
                self.store.record_play(str(removed["raw_title"]))
            self.refresh()
            return removed

    async def move(self, entry_id: str, direction: int) -> bool:
        async with self._lock:
            moved = self.store.move_queue_entry(entry_id, direction)
            self.refresh()
            return moved

    @staticmethod
    def _queue_title_key(title: str) -> str:
        return " ".join(title.casefold().split())

    @classmethod
    def _same_requester(
        cls,
        item: dict[str, Any],
        request_name: str,
        user_id: str | None,
        requester_provider: str,
        requester_provider_id: str,
    ) -> bool:
        if user_id and item.get("user_id") == user_id:
            return True
        if (
            requester_provider
            and requester_provider_id
            and item.get("requester_provider") == requester_provider
            and item.get("requester_provider_id") == requester_provider_id
        ):
            return True
        return cls._queue_title_key(str(item.get("user", ""))) == cls._queue_title_key(request_name)


class TwitchChatBridge:
    def __init__(
        self,
        store: Store,
        queue: QueueBridge,
        client_id: str,
        broadcaster_id: str,
        token_provider: Callable[[], Awaitable[str]],
    ) -> None:
        self.store = store
        self.queue = queue
        self.client_id = client_id
        self.broadcaster_id = broadcaster_id
        self.token_provider = token_provider
        self.task: asyncio.Task[None] | None = None
        self.session: aiohttp.ClientSession | None = None
        self.seen_message_ids: set[str] = set()
        self.connected = False
        self.message_tasks: set[asyncio.Task[None]] = set()
        self.send_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.client_id and self.broadcaster_id and (not self.task or self.task.done()):
            self.task = asyncio.create_task(self._run(), name="twitch-chat")

    async def close(self) -> None:
        message_tasks = list(self.message_tasks)
        for task in message_tasks:
            task.cancel()
        if message_tasks:
            await asyncio.gather(*message_tasks, return_exceptions=True)
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        if self.session and not self.session.closed:
            await self.session.close()

    def announce_request(self, title: str, request_name: str) -> None:
        if self.store.settings()["twitch_announce_requests"]:
            self._schedule_message(f"{request_name} added {title} to the request queue.")

    def announce_queue_status(self, open_: bool) -> None:
        if self.store.settings()["twitch_announce_queue_status"]:
            self._schedule_message(f"The request queue is now {'open' if open_ else 'closed'}.")

    def _schedule_message(self, message: str) -> None:
        task = asyncio.create_task(self._send_message(message), name="twitch-chat-announcement")
        self.message_tasks.add(task)
        task.add_done_callback(self.message_tasks.discard)

    async def _send_message(self, message: str) -> None:
        try:
            token = await self.token_provider()
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
            headers = {
                "Authorization": f"Bearer {token}",
                "Client-Id": self.client_id,
                "Content-Type": "application/json",
            }
            body = {
                "broadcaster_id": self.broadcaster_id,
                "sender_id": self.broadcaster_id,
                "message": message,
            }
            async with self.send_lock:
                async with self.session.post(
                    "https://api.twitch.tv/helix/chat/messages", headers=headers, json=body
                ) as response:
                    result = await response.json(content_type=None)
                    sent = bool(result.get("data") and result["data"][0].get("is_sent"))
                    if response.status >= 400 or not sent:
                        raise RuntimeError(f"Twitch chat message failed ({response.status}): {result}")
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.exception("Could not send Twitch chat announcement")

    async def _run(self) -> None:
        delay = 2
        while True:
            try:
                if not self.store.settings()["twitch_chat_enabled"]:
                    await asyncio.sleep(30)
                    continue
                token = await self.token_provider()
                if not self.session or self.session.closed:
                    self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
                async with self.session.ws_connect("wss://eventsub.wss.twitch.tv/ws", heartbeat=25) as socket:
                    welcome = await socket.receive_json(timeout=15)
                    session_id = welcome["payload"]["session"]["id"]
                    await self._subscribe(session_id, token)
                    self.connected = True
                    delay = 2
                    logging.info("Twitch chat command listener connected")
                    async for message in socket:
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        payload = json.loads(message.data)
                        kind = payload.get("metadata", {}).get("message_type")
                        if kind == "notification":
                            message_id = str(payload.get("metadata", {}).get("message_id") or "")
                            if message_id and message_id in self.seen_message_ids:
                                continue
                            if message_id:
                                self.seen_message_ids.add(message_id)
                                if len(self.seen_message_ids) > 1000:
                                    self.seen_message_ids.clear()
                            await self._handle_chat(payload.get("payload", {}).get("event", {}))
                        elif kind == "session_reconnect":
                            break
            except asyncio.CancelledError:
                raise
            except Exception:
                logging.exception("Twitch chat command listener disconnected")
            finally:
                self.connected = False
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def _subscribe(self, session_id: str, token: str) -> None:
        assert self.session
        headers = {
            "Authorization": f"Bearer {token}",
            "Client-Id": self.client_id,
            "Content-Type": "application/json",
        }
        body = {
            "type": "channel.chat.message",
            "version": "1",
            "condition": {
                "broadcaster_user_id": self.broadcaster_id,
                "user_id": self.broadcaster_id,
            },
            "transport": {"method": "websocket", "session_id": session_id},
        }
        async with self.session.post(
            "https://api.twitch.tv/helix/eventsub/subscriptions", headers=headers, json=body
        ) as response:
            if response.status >= 400:
                detail = await response.text()
                raise RuntimeError(f"Twitch chat subscription failed ({response.status}): {detail}")

    async def _handle_chat(self, event: dict[str, Any]) -> None:
        text = str(event.get("message", {}).get("text") or "").strip()
        requester_id = str(event.get("chatter_user_id") or "")
        requester_name = str(event.get("chatter_user_name") or event.get("chatter_user_login") or "Viewer")
        settings = self.store.settings()
        request_command = str(settings["twitch_request_command"]).strip().casefold()
        remove_command = str(settings["twitch_remove_command"]).strip().casefold()
        command, _, argument = text.partition(" ")
        command = command.casefold()
        if command == request_command and argument.strip():
            candidate = self.store.request_candidate(argument.strip())
            if not candidate:
                return
            if self.store.request_cooldown_remaining_minutes(candidate["song_id"]) is not None:
                return
            user_id = self.store.user_for_identity("twitch", requester_id)
            try:
                await self.queue.request(
                    candidate["title"],
                    requester_name,
                    candidate["grouped_titles"],
                    user_id=user_id,
                    requester_provider="twitch",
                    requester_provider_id=requester_id,
                )
            except (QueueClosedError, QueueLimitError, SongAlreadyQueuedError):
                return
        elif command == remove_command and argument.strip().isdigit():
            index = int(argument.strip()) - 1
            self.queue.refresh()
            if index < 0 or index >= len(self.queue.current_queue):
                return
            item = self.queue.current_queue[index]
            if item.get("requester_provider") == "twitch" and item.get("requester_provider_id") == requester_id:
                await self.queue.remove_by_id(str(item["id"]))


async def hourly_maintenance(store: Store) -> None:
    while True:
        try:
            store.hourly_maintenance()
        except Exception:
            logging.exception("Hourly new-song maintenance failed")
        await asyncio.sleep(60 * 60)
