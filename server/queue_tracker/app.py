from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import aiohttp
from aiohttp import web
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from .database import Store
from .oauth import PROVIDERS, authorize_url, exchange, profile
from .queue import QueueBridge, hourly_maintenance


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

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.cors])
        app.router.add_get("/api/health", self.health)
        app.router.add_get("/api/catalog", self.catalog)
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
        app.router.add_get("/auth/{provider}", self.begin_auth)
        app.router.add_get("/auth/{provider}/callback", self.auth_callback)
        app.on_startup.append(self.startup)
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
        return web.json_response({"ok": True, "queue_connected": self.queue.connected})

    async def catalog(self, _request: web.Request) -> web.Response:
        return web.json_response(self.store.catalog())

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
        try: await self.queue.request(title, name)
        except RuntimeError as error: raise web.HTTPServiceUnavailable(text=f'{{"error":"{str(error)}"}}', content_type="application/json")
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
        self.require_admin(request); body = await self.json(request); raw = self.store.request_title(request.match_info["song_id"])
        if not raw: raise web.HTTPNotFound()
        self.store.save_song_tags(raw, body.get("tags", [])); return web.json_response({"ok": True})

    async def adjust_play(self, request: web.Request) -> web.Response:
        self.require_admin(request); body = await self.json(request); delta = max(-1, min(1, int(body.get("delta", 0)))); self.store.adjust_play(request.match_info["song_id"], delta); return web.json_response({"ok": True})

    def valid_return_to(self, value: str) -> str:
        origin = f"{urlparse(value).scheme}://{urlparse(value).netloc}".rstrip("/")
        if origin not in self.origins: raise web.HTTPBadRequest(text="Unknown return address")
        return value

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
        client_id = os.getenv(f"{provider.upper()}_CLIENT_ID", "")
        client_secret = os.getenv(f"{provider.upper()}_CLIENT_SECRET", "")
        callback = f"{self.public_url}/auth/{provider}/callback"
        assert self.http
        tokens = await exchange(self.http, provider, client_id, client_secret, callback, request.query.get("code", ""))
        identity = await profile(self.http, provider, tokens["access_token"], client_id)
        existing_user = self.store.identity_user(provider, identity["id"])
        if pending["mode"] == "link":
            user_id = pending["user_id"]
            if existing_user and existing_user != user_id: raise web.HTTPConflict(text="That identity belongs to another account")
        else:
            user_id = existing_user or self.store.create_user()
        self.store.save_identity(user_id, provider, identity["id"], identity["name"], identity["avatar"], self.cipher.encrypt(tokens["access_token"].encode()).decode(), self.cipher.encrypt(tokens["refresh_token"].encode()).decode() if tokens["refresh_token"] else "")
        response = web.HTTPFound(pending["return_to"]); self.issue_session(response, user_id); raise response


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    service = Service()
    web.run_app(service.app(), host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8787")))
