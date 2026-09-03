from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import aiohttp


@dataclass(frozen=True)
class Provider:
    authorize: str
    token: str
    profile: str
    scopes: str


PROVIDERS = {
    "twitch": Provider("https://id.twitch.tv/oauth2/authorize", "https://id.twitch.tv/oauth2/token", "https://api.twitch.tv/helix/users", "user:read:email"),
    "discord": Provider("https://discord.com/oauth2/authorize", "https://discord.com/api/v10/oauth2/token", "https://discord.com/api/v10/users/@me", "identify email"),
    "google": Provider("https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", "https://openidconnect.googleapis.com/v1/userinfo", "openid profile email"),
}


def authorize_url(provider: str, client_id: str, callback: str, state: str) -> str:
    config = PROVIDERS[provider]
    values = {"client_id": client_id, "redirect_uri": callback, "response_type": "code", "scope": config.scopes, "state": state}
    if provider == "google": values["access_type"] = "offline"
    return f"{config.authorize}?{urlencode(values)}"


async def exchange(session: aiohttp.ClientSession, provider: str, client_id: str, client_secret: str, callback: str, code: str) -> dict[str, str]:
    config = PROVIDERS[provider]
    form = {"client_id": client_id, "client_secret": client_secret, "code": code, "grant_type": "authorization_code", "redirect_uri": callback}
    async with session.post(config.token, data=form) as response:
        body = await response.json()
        if response.status >= 400: raise RuntimeError(body.get("error_description") or body.get("message") or "OAuth token exchange failed")
        return {"access_token": str(body.get("access_token") or ""), "refresh_token": str(body.get("refresh_token") or "")}


async def profile(session: aiohttp.ClientSession, provider: str, access_token: str, client_id: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if provider == "twitch": headers["Client-Id"] = client_id
    async with session.get(PROVIDERS[provider].profile, headers=headers) as response:
        body: Any = await response.json()
        if response.status >= 400: raise RuntimeError("Could not read OAuth profile")
    if provider == "twitch":
        item = body["data"][0]
        return {"id": str(item["id"]), "name": str(item.get("display_name") or item.get("login") or "Twitch user"), "avatar": str(item.get("profile_image_url") or "")}
    if provider == "discord":
        avatar = f"https://cdn.discordapp.com/avatars/{body['id']}/{body['avatar']}.png" if body.get("avatar") else ""
        return {"id": str(body["id"]), "name": str(body.get("global_name") or body.get("username") or "Discord user"), "avatar": avatar}
    return {"id": str(body["sub"]), "name": str(body.get("name") or body.get("email") or "Google user"), "avatar": str(body.get("picture") or "")}
