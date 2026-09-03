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


if __name__ == "__main__":
    unittest.main()
