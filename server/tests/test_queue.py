import unittest

from queue_tracker.queue import QueueBridge


class QueueTests(unittest.TestCase):
    def test_first_slot_shift_counts_completion(self):
        self.assertEqual(QueueBridge._first_slot_removed(["A", "B", "C"], ["B", "C"]), "A")

    def test_append_does_not_count(self):
        self.assertIsNone(QueueBridge._first_slot_removed(["A"], ["A", "B"]))

    def test_reorder_does_not_count(self):
        self.assertIsNone(QueueBridge._first_slot_removed(["A", "B"], ["B", "A"]))


if __name__ == "__main__":
    unittest.main()
