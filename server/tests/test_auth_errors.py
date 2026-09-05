from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

from queue_tracker.auth_errors import provider_auth_error, return_to_with_error


class AuthErrorTests(unittest.TestCase):
    def test_access_denied_is_reported_as_cancellation_for_every_provider(self) -> None:
        for provider in ("discord", "twitch", "google"):
            with self.subTest(provider=provider):
                self.assertEqual(provider_auth_error(provider, "access_denied"), f"{provider.title()} authentication was cancelled.")

    def test_provider_description_is_used_for_other_errors(self) -> None:
        self.assertEqual(
            provider_auth_error("discord", "temporarily_unavailable", "  Please   try again later.  "),
            "Discord authentication failed: Please try again later.",
        )

    def test_error_redirect_preserves_existing_query_and_fragment(self) -> None:
        result = return_to_with_error("https://songlist.gozarproductions.com/account?source=login#linked", "Discord authentication was cancelled.")
        parsed = urlparse(result)
        self.assertEqual(parsed.fragment, "linked")
        self.assertEqual(parse_qs(parsed.query), {"source": ["login"], "auth_error": ["Discord authentication was cancelled."]})

    def test_error_redirect_replaces_an_old_authentication_error(self) -> None:
        result = return_to_with_error("https://songlist.gozarproductions.com/account?auth_error=old", "new")
        self.assertEqual(parse_qs(urlparse(result).query)["auth_error"], ["new"])


if __name__ == "__main__":
    unittest.main()
