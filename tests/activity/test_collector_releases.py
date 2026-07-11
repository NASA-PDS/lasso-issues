"""Unit tests for collector_releases.py (issue #63)."""
import unittest
import unittest.mock

from lasso.issues.activity.schema import normalize_release


class TestNormalizeRelease(unittest.TestCase):
    """Tests for schema.normalize_release."""

    def _make_release_data(self, tag="v1.0.0", name="Release 1.0.0",
                           published_at="2026-06-01T10:00:00Z",
                           prerelease=False, body="Fixes #12"):
        return {
            "id": 777,
            "tag_name": tag,
            "name": name,
            "published_at": published_at,
            "prerelease": prerelease,
            "body": body,
            "html_url": f"https://github.com/NASA-PDS/testrepo/releases/tag/{tag}",
        }

    def test_basic_normalization(self):
        data = self._make_release_data()
        result = normalize_release(data, "testrepo")

        self.assertEqual(result['id'], 777)
        self.assertEqual(result['repo'], "testrepo")
        self.assertEqual(result['tag'], "v1.0.0")
        self.assertEqual(result['name'], "Release 1.0.0")
        self.assertEqual(result['published_at'], "2026-06-01T10:00:00Z")
        self.assertFalse(result['is_prerelease'])
        self.assertEqual(result['linked_prs'], [])

    def test_prerelease_flagged(self):
        data = self._make_release_data(prerelease=True)
        result = normalize_release(data, "testrepo")
        self.assertTrue(result['is_prerelease'])

    def test_body_truncated_to_500_chars(self):
        long_body = "x" * 600
        data = self._make_release_data(body=long_body)
        result = normalize_release(data, "testrepo")
        self.assertEqual(len(result['body_summary']), 500)

    def test_none_body_normalized_to_empty(self):
        data = self._make_release_data(body=None)
        result = normalize_release(data, "testrepo")
        self.assertEqual(result['body_summary'], "")

    def test_tag_fallback_normalization(self):
        tag_data = {
            "name": "v2.0.0",
            "commit": {"committed_date": "2026-05-15T08:00:00Z"},
            "url": "https://api.github.com/repos/NASA-PDS/testrepo/git/refs/tags/v2.0.0",
        }
        result = normalize_release(tag_data, "testrepo", is_tag_fallback=True)

        self.assertIsNone(result['id'])
        self.assertEqual(result['tag'], "v2.0.0")
        self.assertFalse(result['is_prerelease'])
        self.assertEqual(result['published_at'], "2026-05-15T08:00:00Z")

    def test_name_falls_back_to_tag_name(self):
        data = self._make_release_data(name=None, tag="v3.0.0")
        data['name'] = None
        result = normalize_release(data, "testrepo")
        self.assertEqual(result['name'], "v3.0.0")


class TestParseDateRange(unittest.TestCase):
    """Tests for the _parse_date and _parse_iso helpers."""

    def test_parse_date_start(self):
        from lasso.issues.activity.collector_releases import _parse_date
        from datetime import timezone
        dt = _parse_date("2026-01-15")
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parse_date_end_of_day(self):
        from lasso.issues.activity.collector_releases import _parse_date
        dt = _parse_date("2026-01-15", end_of_day=True)
        self.assertEqual(dt.hour, 23)
        self.assertEqual(dt.second, 59)

    def test_parse_iso_z_suffix(self):
        from lasso.issues.activity.collector_releases import _parse_iso
        dt = _parse_iso("2026-06-01T10:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)

    def test_parse_iso_invalid_returns_none(self):
        from lasso.issues.activity.collector_releases import _parse_iso
        self.assertIsNone(_parse_iso("not-a-date"))


class TestPaginate(unittest.TestCase):
    """Tests for the _paginate helper."""

    def test_single_page_returned(self):
        from lasso.issues.activity.collector_releases import _paginate
        page = [{"id": i} for i in range(50)]
        response = unittest.mock.MagicMock()
        response.status_code = 200
        response.json.return_value = page
        gh = unittest.mock.MagicMock()
        gh.session.get.return_value = response

        result = _paginate(gh, "https://api.github.com/repos/org/repo/releases")
        self.assertEqual(len(result), 50)
        self.assertEqual(gh.session.get.call_count, 1)

    def test_multiple_pages_fetched(self):
        from lasso.issues.activity.collector_releases import _paginate
        full_page = [{"id": i} for i in range(100)]
        partial_page = [{"id": i} for i in range(30)]

        response1 = unittest.mock.MagicMock()
        response1.status_code = 200
        response1.json.return_value = full_page

        response2 = unittest.mock.MagicMock()
        response2.status_code = 200
        response2.json.return_value = partial_page

        gh = unittest.mock.MagicMock()
        gh.session.get.side_effect = [response1, response2]

        result = _paginate(gh, "https://api.github.com/repos/org/repo/releases")
        self.assertEqual(len(result), 130)
        self.assertEqual(gh.session.get.call_count, 2)

    def test_non_200_on_first_page_returns_none(self):
        from lasso.issues.activity.collector_releases import _paginate
        response = unittest.mock.MagicMock()
        response.status_code = 404
        gh = unittest.mock.MagicMock()
        gh.session.get.return_value = response

        result = _paginate(gh, "https://api.github.com/repos/org/repo/releases")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
