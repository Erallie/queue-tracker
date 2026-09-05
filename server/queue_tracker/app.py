from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import aiohttp
from aiohttp import web
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from .auth_errors import provider_auth_error, return_to_with_error
from .database import Store
from .oauth import PROVIDERS, authorize_url, exchange, profile
from .queue import QueueBridge, SongAlreadyQueuedError, hourly_maintenance


class Service:
    def __init__(self) -> None:
        load_dotenv()
        self.public_url = os.getenv("PUBLIC_URL", "http://localhost:8787").rstrip("/")
        self.origins = {value.strip().rstrip("/") for value in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if value.strip()}
        self.store = Store(os.getenv("DATABASE_PATH", "data/queue-tracker.sqlite"))
        key = os.getenv("TOKEN_ENCRYPTION_KEY", "").encode()
        if not key:
            key = Fernet.generate_key()
            logging.warning("TOKEN_ENCRYPTION_KEY is not set; OAuth tokens will not survive a restart")
        self.cipher = Fernet(key)
        self.queue = QueueBridge(self.store)
        self.http: aiohttp.ClientSession | None = None
        self.cookie_name = "queue_tracker_session"
        self.owner_identities = {item.strip() for item in os.getenv("OWNER_IDENTITIES", "").split(",") if item.strip()}
        self.event_tasks: set[asyncio.Task[Any]] = set()
        self.catalog_listeners: set[asyncio.Queue[dict[str, Any]]] = set()
        self.store.on_catalog_changed = self.publish_catalog

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.cors])
        app.router.add_get("/api/health", self.health)
        app.router.add_get("/api/catalog", self.catalog)
        app.router.add_get("/api/catalog/events", self.catalog_events)
        app.router.add_get("/api/queue", self.current_queue)
        app.router.add_get("/api/queue/events", self.queue_events)
        app.router.add_delete("/api/queue/{index}", self.remove_queue_item)
        app.router.add_get("/api/me", self.me)
        app.router.add_post("/api/logout", self.logout)
        app.router.add_delete("/api/identities/{provider}", self.unlink)
        app.router.add_post("/api/songs/{song_id}/request", self.request_song)
        app.router.add_get("/api/admin", self.admin)
        app.router.add_put("/api/admin/settings", self.save_settings)
        app.router.add_put("/api/admin/groups", self.save_groups)
        app.router.add_put("/api/admin/tags", self.save_tags)
        app.router.add_put("/api/admin/songs/{song_id}/tags", self.save_song_tags)
        app.router.add_post("/api/admin/songs/{song_id}/plays", self.adjust_play)
        app.router.add_delete("/api/admin/songs/{song_id}/new", self.remove_new_tag)
        app.router.add_get("/auth/{provider}", self.begin_auth)
        app.router.add_get("/auth/{provider}/callback", self.auth_callback)
        app.on_startup.append(self.startup)
        app.on_shutdown.append(self.shutdown)
        app.on_cleanup.append(self.cleanup)
        return app

    @web.middleware
    async def cors(self, request: web.Request, handler):
        origin = request.headers.get("Origin", "").rstrip("/")
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            try:
                response = await handler(request)
            except web.HTTPException as error:
                response = error
        if origin in self.origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        return response

    async def startup(self, _app: web.Application) -> None:
        self.http = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        await self.queue.start()
        _app["maintenance_task"] = asyncio.create_task(hourly_maintenance(self.store), name="hourly-maintenance")

    async def cleanup(self, app: web.Application) -> None:
        app["maintenance_task"].cancel()
        await self.queue.close()
        if self.http: await self.http.close()
        self.store.close()

    async def shutdown(self, _app: web.Application) -> None:
        tasks = list(self.event_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def user_id(self, request: web.Request) -> str | None:
        token = request.cookies.get(self.cookie_name, "")
        return self.store.session_user(hashlib.sha256(token.encode()).hexdigest()) if token else None

    def require_user(self, request: web.Request) -> str:
        user_id = self.user_id(request)
        if not user_id: raise web.HTTPUnauthorized(text='{"error":"Sign in to continue"}', content_type="application/json")
        return user_id

    def is_admin(self, user_id: str | None) -> bool:
        return bool(user_id and any(f"{item['provider']}:{item['provider_user_id']}" in self.owner_identities for item in self.store.identities(user_id)))

    def require_admin(self, request: web.Request) -> str:
        user_id = self.require_user(request)
        if not self.is_admin(user_id): raise web.HTTPForbidden(text='{"error":"Owner access required"}', content_type="application/json")
        return user_id

    def request_name(self, user_id: str) -> str:
        identities = self.store.identities(user_id)
        for provider in ("twitch", "discord", "google"):
            match = next((item for item in identities if item["provider"] == provider), None)
            if match: return str(match["display_name"])
        return "Guest"

    def issue_session(self, response: web.StreamResponse, user_id: str) -> None:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        self.store.save_session(hashlib.sha256(token.encode()).hexdigest(), user_id, expires)
        response.set_cookie(self.cookie_name, token, max_age=30*86400, httponly=True, secure=self.public_url.startswith("https://"), samesite="None" if self.public_url.startswith("https://") else "Lax", path="/")

    async def json(self, request: web.Request) -> dict:
        try: return await request.json()
        except Exception: raise web.HTTPBadRequest(text='{"error":"Invalid JSON"}', content_type="application/json")

    async def health(self, _request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "queue_connected": self.queue.connected, "queue_requests_configured": bool(self.queue.auth_cookie)})

    async def catalog(self, _request: web.Request) -> web.Response:
        return web.json_response(self.store.catalog())

    def publish_catalog(self) -> None:
        snapshot = self.store.catalog()
        for listener in self.catalog_listeners:
            if listener.full():
                listener.get_nowait()
            listener.put_nowait(snapshot)

    async def catalog_events(self, request: web.Request) -> web.StreamResponse:
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        }
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin in self.origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Vary"] = "Origin"
        response = web.StreamResponse(headers=headers)
        await response.prepare(request)
        listener: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1)
        listener.put_nowait(self.store.catalog())
        self.catalog_listeners.add(listener)
        task = asyncio.current_task()
        if task:
            self.event_tasks.add(task)
        try:
            while True:
                try:
                    catalog = await asyncio.wait_for(listener.get(), timeout=20)
                    await response.write(f"event: catalog\ndata: {json.dumps(catalog)}\n\n".encode())
                except TimeoutError:
                    await response.write(b": keepalive\n\n")
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.catalog_listeners.discard(listener)
            if task:
                self.event_tasks.discard(task)
        return response

    def queue_for_user(self, user_id: str | None, queue: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
        snapshot = queue if queue is not None else self.queue.current_queue
        owned = self.store.owned_queue_indexes(user_id, snapshot)
        return [{**item, "can_remove": index in owned} for index, item in enumerate(snapshot)]

    async def current_queue(self, request: web.Request) -> web.Response:
        return web.json_response({"queue": self.queue_for_user(self.user_id(request)), "connected": self.queue.connected, "queue_open": self.queue.queue_open})

    async def queue_events(self, request: web.Request) -> web.StreamResponse:
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        }
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin in self.origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Vary"] = "Origin"
        response = web.StreamResponse(headers=headers)
        await response.prepare(request)
        listener = self.queue.subscribe()
        task = asyncio.current_task()
        if task:
            self.event_tasks.add(task)
        try:
            while True:
                try:
                    queue = await asyncio.wait_for(listener.get(), timeout=20)
                    payload = {"queue": self.queue_for_user(self.user_id(request), queue), "connected": self.queue.connected, "queue_open": self.queue.queue_open}
                    await response.write(f"event: queue\ndata: {json.dumps(payload)}\n\n".encode())
                except TimeoutError:
                    await response.write(b": keepalive\n\n")
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self.queue.unsubscribe(listener)
            if task:
                self.event_tasks.discard(task)
        return response

    async def remove_queue_item(self, request: web.Request) -> web.Response:
        user_id = self.require_user(request)
        try:
            index = int(request.match_info["index"])
        except ValueError:
            raise web.HTTPBadRequest(text='{"error":"Invalid queue position"}', content_type="application/json")
        queue = self.queue.current_queue
        if index < 0 or index >= len(queue):
            raise web.HTTPNotFound(text='{"error":"That request is no longer in the queue"}', content_type="application/json")
        if index not in self.store.owned_queue_indexes(user_id, queue):
            raise web.HTTPForbidden(text='{"error":"You can only remove your own requests"}', content_type="application/json")
        item = dict(queue[index])
        try:
            await self.queue.remove(index, item["title"], item["user"])
        except RuntimeError as error:
            return web.json_response({"error": str(error)}, status=503)
        self.store.mark_request_removed(user_id, item["title"], item["user"])
        return web.json_response({"removed": True})

    async def me(self, request: web.Request) -> web.Response:
        user_id = self.user_id(request)
        return web.json_response({"authenticated": bool(user_id), "is_admin": self.is_admin(user_id), "request_name": self.request_name(user_id) if user_id else None, "identities": self.store.identities(user_id) if user_id else []})

    async def logout(self, request: web.Request) -> web.Response:
        token = request.cookies.get(self.cookie_name, "")
        if token: self.store.delete_session(hashlib.sha256(token.encode()).hexdigest())
        response = web.json_response({"ok": True}); response.del_cookie(self.cookie_name, path="/"); return response

    async def unlink(self, request: web.Request) -> web.Response:
        user_id = self.require_user(request)
        provider = request.match_info["provider"]
        if provider not in PROVIDERS: raise web.HTTPNotFound()
        deleted = self.store.unlink_identity(user_id, provider)
        response = web.json_response({"account_deleted": deleted})
        if deleted: response.del_cookie(self.cookie_name, path="/")
        return response

    async def request_song(self, request: web.Request) -> web.Response:
        user_id = self.require_user(request)
        title = self.store.request_title(request.match_info["song_id"])
        if not title: raise web.HTTPNotFound(text='{"error":"Song not found"}', content_type="application/json")
        name = self.request_name(user_id)
        try:
            await self.queue.request(title, name, self.store.group_request_titles(request.match_info["song_id"]))
        except SongAlreadyQueuedError as error:
            return web.json_response({"error": str(error)}, status=409)
        except RuntimeError as error:
            return web.json_response({"error": str(error)}, status=503)
        self.store.record_request(user_id, title, name)
        return web.json_response({"queued": True, "message": f"{title} was requested for {name}"})

    async def admin(self, request: web.Request) -> web.Response:
        self.require_admin(request)
        return web.json_response({"settings": self.store.settings(), "groups": self.store.groups(), "catalog": self.store.catalog()})

    async def save_settings(self, request: web.Request) -> web.Response:
        self.require_admin(request); self.store.save_settings(await self.json(request)); return web.json_response({"ok": True})

    async def save_groups(self, request: web.Request) -> web.Response:
        self.require_admin(request); body = await self.json(request); self.store.save_groups(body.get("groups", [])); return web.json_response({"ok": True})

    async def save_tags(self, request: web.Request) -> web.Response:
        self.require_admin(request); body = await self.json(request); self.store.save_tags(body.get("tags", [])); return web.json_response({"ok": True})

    async def save_song_tags(self, request: web.Request) -> web.Response:
        self.require_admin(request); body = await self.json(request)
        if not self.store.save_song_tags_for_id(request.match_info["song_id"], body.get("tags", [])):
            raise web.HTTPNotFound()
        return web.json_response({"ok": True})

    async def adjust_play(self, request: web.Request) -> web.Response:
        self.require_admin(request)
        body = await self.json(request)
        delta = max(-1, min(1, int(body.get("delta", 0))))
        song_id = request.match_info["song_id"]
        self.store.adjust_play(song_id, delta)
        song = next((item for item in self.store.catalog()["songs"] if item["id"] == song_id), None)
        if not song:
            raise web.HTTPNotFound(text='{"error":"Song not found"}', content_type="application/json")
        return web.json_response({"song": song})

    async def remove_new_tag(self, request: web.Request) -> web.Response:
        self.require_admin(request)
        if not self.store.remove_new_tag(request.match_info["song_id"]):
            raise web.HTTPNotFound(text='{"error":"Song not found"}', content_type="application/json")
        return web.json_response({"ok": True})

    def valid_return_to(self, value: str) -> str:
        origin = f"{urlparse(value).scheme}://{urlparse(value).netloc}".rstrip("/")
        if origin not in self.origins: raise web.HTTPBadRequest(text="Unknown return address")
        return value

    def auth_error_redirect(self, return_to: str, message: str) -> web.HTTPFound:
        return web.HTTPFound(return_to_with_error(return_to, message))

    async def begin_auth(self, request: web.Request) -> web.Response:
        provider = request.match_info["provider"]
        if provider not in PROVIDERS: raise web.HTTPNotFound()
        mode = request.query.get("mode", "login")
        user_id = self.user_id(request)
        if mode == "link" and not user_id: raise web.HTTPUnauthorized(text="Sign in before linking another account")
        return_to = self.valid_return_to(request.query.get("return_to", next(iter(self.origins))))
        client_id = os.getenv(f"{provider.upper()}_CLIENT_ID", "")
        if not client_id: raise web.HTTPServiceUnavailable(text=f"{provider.title()} sign-in is not configured")
        state = secrets.token_urlsafe(32); self.store.save_oauth_state(state, provider, mode, user_id, return_to)
        callback = f"{self.public_url}/auth/{provider}/callback"
        raise web.HTTPFound(authorize_url(provider, client_id, callback, state))

    async def auth_callback(self, request: web.Request) -> web.Response:
        provider = request.match_info["provider"]
        pending = self.store.pop_oauth_state(request.query.get("state", ""))
        if not pending or pending["provider"] != provider: raise web.HTTPBadRequest(text="This sign-in attempt expired. Please try again.")
        provider_error = request.query.get("error", "")
        if provider_error:
            message = provider_auth_error(provider, provider_error, request.query.get("error_description", ""))
            logging.info("%s OAuth callback returned %s", provider.title(), provider_error)
            raise self.auth_error_redirect(pending["return_to"], message)
        client_id = os.getenv(f"{provider.upper()}_CLIENT_ID", "")
        client_secret = os.getenv(f"{provider.upper()}_CLIENT_SECRET", "")
        callback = f"{self.public_url}/auth/{provider}/callback"
        assert self.http
        try:
            tokens = await exchange(self.http, provider, client_id, client_secret, callback, request.query.get("code", ""))
            identity = await profile(self.http, provider, tokens["access_token"], client_id)
        except RuntimeError as error:
            logging.warning("%s OAuth failed: %s", provider.title(), error)
            raise self.auth_error_redirect(pending["return_to"], provider_auth_error(provider, "oauth_failed", str(error)))
        except Exception:
            logging.exception("Unexpected %s OAuth failure", provider.title())
            raise self.auth_error_redirect(pending["return_to"], f"{provider.title()} authentication could not be completed. Please try again.")
        existing_user = self.store.identity_user(provider, identity["id"])
        if pending["mode"] == "link":
            user_id = pending["user_id"]
            if existing_user and existing_user != user_id:
                raise self.auth_error_redirect(pending["return_to"], f"That {provider.title()} identity belongs to another account.")
        else:
            user_id = existing_user or self.store.create_user()
        self.store.save_identity(user_id, provider, identity["id"], identity["name"], identity["avatar"], self.cipher.encrypt(tokens["access_token"].encode()).decode(), self.cipher.encrypt(tokens["refresh_token"].encode()).decode() if tokens["refresh_token"] else "")
        response = web.HTTPFound(pending["return_to"]); self.issue_session(response, user_id); raise response


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    service = Service()
    web.run_app(
        service.app(),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8787")),
        shutdown_timeout=5,
    )
