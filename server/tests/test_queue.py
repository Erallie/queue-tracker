import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace

sys.modules.setdefault("aiohttp", SimpleNamespace())

from queue_tracker.database import Store
from queue_tracker.queue import QueueBridge, QueueClosedError, QueueLimitError, SongAlreadyQueuedError


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

    async def test_ungrouped_duplicate_is_rejected(self):
        await self.queue.request("Song (Show)", "One")
        with self.assertRaisesRegex(SongAlreadyQueuedError, "already in the queue"):
            await self.queue.request("Song (Show)", "Two")
        self.assertEqual(len(self.queue.current_queue), 1)

    async def test_per_person_pending_request_limit_is_enforced(self):
        await self.queue.request("First (Show)", "Viewer", requester_provider="twitch", requester_provider_id="123")
        with self.assertRaisesRegex(QueueLimitError, "already have requests pending"):
            await self.queue.request("Second (Show)", "Viewer", requester_provider="twitch", requester_provider_id="123")
        await self.queue.request("Second (Show)", "Other Viewer", requester_provider="twitch", requester_provider_id="456")
        self.assertEqual(len(self.queue.current_queue), 2)

    async def test_per_person_pending_request_limit_can_be_disabled(self):
        self.store.save_settings({"queue_limit_per_person": 0})
        await self.queue.request("First (Show)", "Viewer")
        await self.queue.request("Second (Show)", "Viewer")
        self.assertEqual(len(self.queue.current_queue), 2)

    async def test_queue_closes_after_configured_number_of_new_requests(self):
        await self.queue.set_open(True, 2)
        await self.queue.request("First (Show)", "One")
        self.assertTrue(self.queue.queue_open)
        self.assertEqual(self.queue.close_after, 1)
        await self.queue.request("Second (Show)", "Two")
        self.assertFalse(self.queue.queue_open)
        self.assertEqual(self.queue.close_after, 0)

    async def test_cancelling_restores_an_automatic_close_slot(self):
        await self.queue.set_open(True, 2)
        await self.queue.request("First (Show)", "One")
        first_id = self.queue.current_queue[0]["id"]
        await self.queue.remove_by_id(first_id)
        self.assertTrue(self.queue.queue_open)
        self.assertEqual(self.queue.close_after, 2)

        await self.queue.request("Second (Show)", "Two")
        await self.queue.request("Third (Show)", "Three")
        self.assertFalse(self.queue.queue_open)
        third_id = self.queue.current_queue[-1]["id"]
        await self.queue.remove_by_id(third_id)
        self.assertTrue(self.queue.queue_open)
        self.assertEqual(self.queue.close_after, 1)

    async def test_completing_does_not_restore_an_automatic_close_slot(self):
        await self.queue.set_open(True, 1)
        await self.queue.request("Song (Show)", "Viewer")
        entry_id = self.queue.current_queue[0]["id"]
        await self.queue.complete(entry_id)
        self.assertFalse(self.queue.queue_open)
        self.assertEqual(self.queue.close_after, 0)

    async def test_complete_removes_and_records_play(self):
        song = next(item for item in self.store.catalog()["songs"] if item["title"] == "Pandemonium")
        title = self.store.request_title(song["id"])
        await self.queue.request(title, "Viewer")
        entry_id = self.queue.current_queue[0]["id"]
        await self.queue.complete(entry_id)
        updated = next(item for item in self.store.catalog()["songs"] if item["id"] == song["id"])
        self.assertEqual(updated["play_count"], 1)
        self.assertEqual(self.queue.current_queue, [])

    async def test_queue_items_can_be_moved_and_order_is_persisted(self):
        for index, title in enumerate(("First (Show)", "Second (Show)", "Third (Show)")):
            await self.queue.request(title, f"Viewer {index}")
        third_id = self.queue.current_queue[2]["id"]
        self.assertTrue(await self.queue.move(third_id, -1))
        self.assertEqual(
            [entry["title"] for entry in self.queue.current_queue],
            ["First (Show)", "Third (Show)", "Second (Show)"],
        )
        self.assertEqual(
            [entry["title"] for entry in self.store.queue_entries()],
            ["First (Show)", "Third (Show)", "Second (Show)"],
        )
        self.assertFalse(await self.queue.move(self.queue.current_queue[0]["id"], -1))


if __name__ == "__main__":
    unittest.main()
