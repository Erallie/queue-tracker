import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace

sys.modules.setdefault("aiohttp", SimpleNamespace())

from queue_tracker.database import Store
from queue_tracker.queue import QueueBridge, QueueClosedError, SongAlreadyQueuedError


class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.directory.name) / "queue-tracker.sqlite"))
        self.store.set_queue_open(True)
        self.queue = QueueBridge(self.store)
        await self.queue.start()

    async def asyncTearDown(self):
        self.store.close()
        self.directory.cleanup()

    async def test_request_is_persisted_and_published(self):
        listener = self.queue.subscribe()
        await listener.get()
        site_user = self.store.create_user()
        await self.queue.request("Song (Show)", "Viewer", user_id=site_user)
        update = await listener.get()
        self.assertEqual(update[0]["title"], "Song (Show)")
        self.assertEqual(update[0]["user"], "Viewer")
        self.assertEqual(self.store.queue_entries()[0]["user_id"], site_user)

    async def test_closed_queue_rejects_requests(self):
        await self.queue.set_open(False)
        with self.assertRaisesRegex(QueueClosedError, "closed"):
            await self.queue.request("Song (Show)", "Viewer")

    async def test_group_request_is_blocked_when_any_member_is_queued(self):
        await self.queue.request("Alternate Version (Show)", "Viewer")
        with self.assertRaisesRegex(SongAlreadyQueuedError, "already in the queue"):
            await self.queue.request(
                "Primary Version (Show)",
                "Viewer",
                ["Primary Version (Show)", "Alternate Version (Show)"],
            )

    async def test_ungrouped_duplicate_is_allowed(self):
        await self.queue.request("Song (Show)", "One")
        await self.queue.request("Song (Show)", "Two")
        self.assertEqual(len(self.queue.current_queue), 2)

    async def test_complete_removes_and_records_play(self):
        song = next(item for item in self.store.catalog()["songs"] if item["title"] == "Pandemonium")
        title = self.store.request_title(song["id"])
        await self.queue.request(title, "Viewer")
        entry_id = self.queue.current_queue[0]["id"]
        await self.queue.complete(entry_id)
        updated = next(item for item in self.store.catalog()["songs"] if item["id"] == song["id"])
        self.assertEqual(updated["play_count"], 1)
        self.assertEqual(self.queue.current_queue, [])


if __name__ == "__main__":
    unittest.main()
