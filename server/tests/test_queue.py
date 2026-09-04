import asyncio
import unittest

from queue_tracker.queue import QueueBridge


class QueueTests(unittest.TestCase):
    def test_first_slot_shift_counts_completion(self):
        self.assertEqual(QueueBridge._first_slot_removed(["A", "B", "C"], ["B", "C"]), "A")

    def test_append_does_not_count(self):
        self.assertIsNone(QueueBridge._first_slot_removed(["A"], ["A", "B"]))

    def test_reorder_does_not_count(self):
        self.assertIsNone(QueueBridge._first_slot_removed(["A", "B"], ["B", "A"]))


class FakeStore:
    def settings(self):
        return {}


class FakeSocket:
    closed = False

    def __init__(self):
        self.sent = []

    async def send_json(self, payload):
        self.sent.append(payload)


class QueueRequestTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge = QueueBridge(FakeStore())
        self.bridge.auth_cookie = "session=test"
        self.bridge.socket = FakeSocket()

    async def test_request_waits_for_success_confirmation(self):
        pending = asyncio.create_task(self.bridge.request("Song (Show)", "Viewer"))
        await asyncio.sleep(0)
        self.bridge._handle({"cmd": "choose", "selection": "Song (Show)"})
        await pending
        self.assertEqual(self.bridge.socket.sent, [{"cmd": "choose", "selection": "Song (Show)", "added_for": "Viewer"}])

    async def test_request_surfaces_mustardmine_error(self):
        pending = asyncio.create_task(self.bridge.request("Song (Show)", "Viewer"))
        await asyncio.sleep(0)
        self.bridge._handle({"cmd": "choose", "error": "Not logged in"})
        with self.assertRaisesRegex(RuntimeError, "Not logged in"):
            await pending

    async def test_queue_update_can_confirm_request(self):
        pending = asyncio.create_task(self.bridge.request("Song (Show)", "Viewer"))
        await asyncio.sleep(0)
        self.bridge._handle({"cmd": "update", "queue": [{"title": "Song (Show)", "user": "Viewer"}]})
        await pending

    async def test_queue_update_confirms_when_requester_field_is_absent(self):
        pending = asyncio.create_task(self.bridge.request("Song (Show)", "Viewer"))
        await asyncio.sleep(0)
        self.bridge._handle({"cmd": "update", "queue": [{"title": "Song (Show)"}]})
        await pending

    async def test_queue_update_is_published_to_every_listener(self):
        first = self.bridge.subscribe()
        second = self.bridge.subscribe()
        await first.get()
        await second.get()
        expected = [{"title": "Song (Show)", "user": "Viewer"}]
        self.bridge._handle({"cmd": "update", "queue": expected})
        self.assertEqual(await first.get(), expected)
        self.assertEqual(await second.get(), expected)

    async def test_queue_update_tracks_open_and_closed_state(self):
        self.bridge._handle({"cmd": "update", "queue": [], "queue_open": 1})
        self.assertIs(self.bridge.queue_open, True)
        self.bridge._handle({"cmd": "update", "queue": [], "queue_open": 0})
        self.assertIs(self.bridge.queue_open, False)

    async def test_request_command_cannot_be_overridden(self):
        pending = asyncio.create_task(self.bridge.request("Song (Show)", "Viewer"))
        await asyncio.sleep(0)
        self.bridge._handle({"cmd": "choose", "selection": "Song (Show)"})
        await pending
        self.assertEqual(self.bridge.socket.sent[0]["cmd"], "choose")


if __name__ == "__main__":
    unittest.main()
