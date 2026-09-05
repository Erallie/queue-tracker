from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse


def provider_auth_error(provider: str, code: str, description: str = "") -> str:
    name = provider.title()
    if code == "access_denied":
        return f"{name} authentication was cancelled."
    detail = " ".join(description.split())[:240]
    return f"{name} authentication failed: {detail}" if detail else f"{name} authentication failed. Please try again."


def return_to_with_error(return_to: str, message: str) -> str:
    parsed = urlparse(return_to)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key != "auth_error"]
    query.append(("auth_error", message))
    return parsed._replace(query=urlencode(query)).geturl()
