"""Small regression checks for timestamp forms found and supported by the parser."""
from datetime import timezone
import unittest

from timestamps import parse_timestamp


class TimestampParserTests(unittest.TestCase):
    def test_dataset_utc_z_form(self):
        self.assertEqual(parse_timestamp("2026-09-06T11:00:00Z").isoformat(), "2026-09-06T11:00:00+00:00")

    def test_explicit_offset(self):
        self.assertEqual(parse_timestamp("2026-09-06T16:30:00+05:30").isoformat(), "2026-09-06T11:00:00+00:00")

    def test_doubled_z_and_zone(self):
        self.assertEqual(parse_timestamp("2026-09-06T11:00:00Z+00:00").isoformat(), "2026-09-06T11:00:00+00:00")
        self.assertEqual(parse_timestamp("2026-09-06T11:00:00+00:00Z").isoformat(), "2026-09-06T11:00:00+00:00")

    def test_naive_assumed_utc(self):
        self.assertEqual(parse_timestamp("2026-09-06T11:00:00").tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
