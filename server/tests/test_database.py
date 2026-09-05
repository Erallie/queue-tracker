import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from queue_tracker.database import Store


class DatabaseTests(unittest.TestCase):
    def test_catalog_change_callback_runs_after_play_update(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                notifications = []
                store.on_catalog_changed = lambda: notifications.append(store.catalog())
                song = next(item for item in store.catalog()["songs"] if item["title"] == "Pandemonium")
                store.adjust_play(song["id"], 1)
                self.assertEqual(len(notifications), 1)
                updated = next(item for item in notifications[0]["songs"] if item["id"] == song["id"])
                self.assertEqual(updated["play_count"], 1)
            finally:
                store.close()

    def test_catalog_uses_configured_artist_when_parenthetical_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Originals\nMy Original", "default_artist": "Erallie"})
                song = store.catalog()["songs"][0]
                self.assertEqual(song["title"], "My Original")
                self.assertEqual(song["parenthetical"], "Erallie")
            finally:
                store.close()

    def test_catalog_sort_prefers_never_played_then_oldest_played(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Songs\nRecent (Same)\nNever (Same)\nOldest (Same)"})
                songs = {item["title"]: item for item in store.catalog()["songs"]}
                with patch("queue_tracker.database.now", return_value="2026-01-01T12:00:00+00:00"):
                    store.adjust_play(songs["Oldest"]["id"], 1)
                with patch("queue_tracker.database.now", return_value="2026-09-01T12:00:00+00:00"):
                    store.adjust_play(songs["Recent"]["id"], 1)

                ordered = [item["title"] for item in store.catalog()["songs"]]
                self.assertEqual(ordered, ["Never", "Oldest", "Recent"])
            finally:
                store.close()

    def test_catalog_sort_uses_play_count_within_same_played_day(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Songs\nMore Plays (Zulu)\nFewer Plays (Alpha)\nSame Count B (Beta)\nSame Count A (Alpha)"})
                songs = {item["title"]: item for item in store.catalog()["songs"]}
                times = {
                    "More Plays": ["2026-09-01T01:00:00+00:00", "2026-09-01T23:00:00+00:00"],
                    "Fewer Plays": ["2026-09-01T22:00:00+00:00"],
                    "Same Count B": ["2026-09-01T20:00:00+00:00"],
                    "Same Count A": ["2026-09-01T21:00:00+00:00"],
                }
                for title, played_at_values in times.items():
                    for played_at in played_at_values:
                        with patch("queue_tracker.database.now", return_value=played_at):
                            store.adjust_play(songs[title]["id"], 1)

                ordered = [item["title"] for item in store.catalog()["songs"]]
                self.assertEqual(ordered, ["Fewer Plays", "Same Count A", "Same Count B", "More Plays"])
            finally:
                store.close()

    def test_catalog_sort_ignores_leading_articles_without_changing_names(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Songs\nAlpha (Bananas)\nZebra (The Apples)\nThe Apple (Same)\nBanana (Same)\nA Cherry (Same)\nAn Date (Same)"})
                songs = store.catalog()["songs"]
                names = [(song["title"], song["parenthetical"]) for song in songs]
                self.assertEqual(
                    names,
                    [
                        ("Zebra", "The Apples"),
                        ("Alpha", "Bananas"),
                        ("The Apple", "Same"),
                        ("Banana", "Same"),
                        ("A Cherry", "Same"),
                        ("An Date", "Same"),
                    ],
                )
            finally:
                store.close()

    def test_non_new_song_can_be_adjusted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                song = next(
                    item
                    for item in store.catalog()["songs"]
                    if item["title"] == "Pandemonium"
                )
                self.assertFalse(song["is_new"])

                store.adjust_play(song["id"], 1)
                updated = next(
                    item
                    for item in store.catalog()["songs"]
                    if item["id"] == song["id"]
                )
                self.assertEqual(updated["play_count"], 1)

                store.adjust_play(song["id"], -1)
                updated = next(
                    item
                    for item in store.catalog()["songs"]
                    if item["id"] == song["id"]
                )
                self.assertEqual(updated["play_count"], 0)
            finally:
                store.close()

    def test_group_request_titles_include_public_group_name(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Songs\nFirst (Show)\nSecond (Show)"})
                store.save_groups([{"display_name": "Combined (Show)", "members": ["First (Show)", "Second (Show)"]}])
                group = store.catalog()["songs"][0]
                self.assertEqual(
                    store.group_request_titles(group["id"]),
                    ["Combined (Show)", "First (Show)", "Second (Show)"],
                )
            finally:
                store.close()

    def test_decrement_restores_previous_last_played_time(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                song = next(item for item in store.catalog()["songs"] if item["title"] == "Pandemonium")
                first = "2026-08-01T12:00:00+00:00"
                second = "2026-09-01T18:30:00+00:00"
                with patch("queue_tracker.database.now", side_effect=[first, second]):
                    store.adjust_play(song["id"], 1)
                    store.adjust_play(song["id"], 1)

                played_twice = next(item for item in store.catalog()["songs"] if item["id"] == song["id"])
                self.assertEqual(played_twice["last_played"], second)
                self.assertEqual(played_twice["play_count"], 2)

                store.adjust_play(song["id"], -1)
                rolled_back = next(item for item in store.catalog()["songs"] if item["id"] == song["id"])
                self.assertEqual(rolled_back["last_played"], first)
                self.assertEqual(rolled_back["play_count"], 1)
            finally:
                store.close()

    def test_group_decrement_removes_latest_member_play(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Songs\nFirst (Show)\nSecond (Show)"})
                store.save_groups([{"display_name": "Combined (Show)", "members": ["First (Show)", "Second (Show)"]}])
                group = store.catalog()["songs"][0]
                with patch("queue_tracker.database.now", return_value="2026-08-01T12:00:00+00:00"):
                    store.record_play("First (Show)")
                with patch("queue_tracker.database.now", return_value="2026-09-01T18:30:00+00:00"):
                    store.record_play("Second (Show)")

                store.adjust_play(group["id"], -1)
                rolled_back = store.catalog()["songs"][0]
                self.assertEqual(rolled_back["last_played"], "2026-08-01T12:00:00+00:00")
                self.assertEqual(rolled_back["play_count"], 1)
            finally:
                store.close()

    def test_group_shares_one_limited_date_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({
                    "song_text": "# Songs\nFirst (Show)\nSecond (Show)",
                    "last_played_history_limit": 2,
                })
                store.save_groups([{"display_name": "Combined (Show)", "members": ["First (Show)", "Second (Show)"]}])
                group = store.catalog()["songs"][0]
                times = [
                    "2026-07-01T12:00:00+00:00",
                    "2026-08-01T12:00:00+00:00",
                    "2026-09-01T12:00:00+00:00",
                ]
                with patch("queue_tracker.database.now", return_value=times[0]):
                    store.record_play("First (Show)")
                with patch("queue_tracker.database.now", return_value=times[1]):
                    store.record_play("Second (Show)")
                with patch("queue_tracker.database.now", return_value=times[2]):
                    store.record_play("First (Show)")

                current = store.catalog()["songs"][0]
                self.assertEqual(current["play_count"], 3)
                self.assertEqual(current["last_played"], times[2])
                member_dates = {
                    row["last_played"]
                    for row in store.db.execute(
                        "SELECT last_played FROM songs WHERE raw_title IN ('First (Show)','Second (Show)')"
                    )
                }
                self.assertEqual(member_dates, {times[2]})
                retained = store.db.execute(
                    "SELECT COUNT(*) FROM play_events WHERE raw_title IN ('First (Show)','Second (Show)')"
                ).fetchone()[0]
                self.assertEqual(retained, 2)

                store.adjust_play(group["id"], -1)
                previous = store.catalog()["songs"][0]
                self.assertEqual(previous["play_count"], 2)
                self.assertEqual(previous["last_played"], times[1])

                store.adjust_play(group["id"], -1)
                beyond_retained_history = store.catalog()["songs"][0]
                self.assertEqual(beyond_retained_history["play_count"], 1)
                self.assertIsNone(beyond_retained_history["last_played"])
            finally:
                store.close()

    def test_creating_group_combines_member_tags_counts_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({
                    "song_text": "# Songs\nFirst (Show)\nSecond (Show)",
                    "last_played_history_limit": 2,
                })
                songs = {item["title"]: item for item in store.catalog()["songs"]}
                store.save_tags([
                    {"name": "New", "points": 0, "color": "#d33355"},
                    {"name": "First tag", "points": 1, "color": "#111111"},
                    {"name": "Second tag", "points": 2, "color": "#222222"},
                ])
                store.save_song_tags("First (Show)", ["First tag"])
                store.save_song_tags("Second (Show)", ["Second tag"])
                with patch("queue_tracker.database.now", return_value="2026-07-01T12:00:00+00:00"):
                    store.adjust_play(songs["First"]["id"], 1)
                with patch("queue_tracker.database.now", return_value="2026-08-01T12:00:00+00:00"):
                    store.adjust_play(songs["Second"]["id"], 1)
                with patch("queue_tracker.database.now", return_value="2026-09-01T12:00:00+00:00"):
                    store.adjust_play(songs["First"]["id"], 1)

                store.save_groups([{
                    "display_name": "Combined (Show)",
                    "members": ["First (Show)", "Second (Show)"],
                }])

                group = store.catalog()["songs"][0]
                self.assertEqual(group["title"], "Combined")
                self.assertEqual(group["tags"], ["First tag", "Second tag"])
                self.assertEqual(group["play_count"], 3)
                self.assertEqual(group["last_played"], "2026-09-01T12:00:00+00:00")
                retained = store.db.execute(
                    "SELECT COUNT(*) FROM play_events WHERE raw_title IN ('First (Show)','Second (Show)')"
                ).fetchone()[0]
                self.assertEqual(retained, 2)
                member_dates = {
                    row["last_played"]
                    for row in store.db.execute(
                        "SELECT last_played FROM songs WHERE raw_title IN ('First (Show)','Second (Show)')"
                    )
                }
                self.assertEqual(member_dates, {"2026-09-01T12:00:00+00:00"})

                store.save_song_tags_for_id(group["id"], ["First tag"])
                grouped_assignments = {
                    row["raw_title"]: {tag["tag_name"] for tag in store.db.execute(
                        "SELECT tag_name FROM song_tags WHERE raw_title=?", (row["raw_title"],)
                    )}
                    for row in store.db.execute(
                        "SELECT raw_title FROM songs WHERE raw_title IN ('First (Show)','Second (Show)')"
                    )
                }
                self.assertEqual(grouped_assignments, {
                    "First (Show)": {"First tag"},
                    "Second (Show)": {"First tag"},
                })
            finally:
                store.close()

    def test_adding_new_to_one_group_member_updates_every_member_line(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Songs\nFirst (Show)\nSecond (Show)"})
                store.save_groups([{
                    "display_name": "Combined (Show)",
                    "members": ["First (Show)", "Second (Show)"],
                }])

                store.save_settings({"song_text": "# Songs\nFirst (Show) [New]\nSecond (Show)"})

                self.assertEqual(
                    store.settings()["song_text"],
                    "# Songs\nFirst (Show) [New]\nSecond (Show) [New]",
                )
                member_states = {
                    bool(row["is_new"])
                    for row in store.db.execute(
                        "SELECT is_new FROM songs WHERE raw_title IN ('First (Show)','Second (Show)')"
                    )
                }
                self.assertEqual(member_states, {True})
            finally:
                store.close()

    def test_new_tag_can_be_removed_from_a_song(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                song = next(item for item in store.catalog()["songs"] if item["is_new"] and not item["id"].startswith("group:"))
                self.assertTrue(store.remove_new_tag(song["id"]))
                updated = next(item for item in store.catalog()["songs"] if item["id"] == song["id"])
                self.assertFalse(updated["is_new"])
                self.assertNotIn("[New]", next(line for line in store.settings()["song_text"].splitlines() if song["title"] in line))
            finally:
                store.close()

    def test_new_tag_removal_clears_every_member_of_a_group(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "queue-tracker.sqlite"))
            try:
                store.save_settings({"song_text": "# Songs\nFirst (Show) [New]\nSecond (Show) [New]"})
                store.save_groups([{"display_name": "Combined (Show)", "members": ["First (Show)", "Second (Show)"]}])
                song = store.catalog()["songs"][0]
                self.assertTrue(song["is_new"])
                self.assertTrue(store.remove_new_tag(song["id"]))
                self.assertFalse(store.catalog()["songs"][0]["is_new"])
                self.assertNotIn("[New]", store.settings()["song_text"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
