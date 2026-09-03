import unittest

from queue_tracker.catalog import parse_song_text, remove_new_marker, split_name


class CatalogTests(unittest.TestCase):
    def test_ignores_intro_notes_and_headings(self):
        songs = parse_song_text("intro\n# Musical\n*(by title)*\n\nSong (Show) [New]\n## A:\nOther (Artist)")
        self.assertEqual([song.raw_title for song in songs], ["Song (Show)", "Other (Artist)"])
        self.assertTrue(songs[0].is_new)
        self.assertEqual(songs[0].parenthetical, "Show")

    def test_name_uses_final_parenthetical(self):
        self.assertEqual(split_name("Title (with note) (Artist)"), ("Title (with note)", "Artist"))

    def test_remove_new_preserves_layout(self):
        value = "# Songs\nSong (Artist) [New]\nOther (Artist) [New]"
        self.assertEqual(remove_new_marker(value, {"Song (Artist)"}), "# Songs\nSong (Artist)\nOther (Artist) [New]")


if __name__ == "__main__":
    unittest.main()
