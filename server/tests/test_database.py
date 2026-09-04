import tempfile
import unittest
from pathlib import Path

from queue_tracker.database import Store


class DatabaseTests(unittest.TestCase):
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
