"""Tests for Trakt normalization purity and non-blocking concurrent poster enrichment (M-3)."""

from __future__ import annotations

import asyncio
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from workers.importers import trakt as trakt_mod
from workers.importers.trakt import TraktConnector


class TraktNormalizePurityTests(unittest.TestCase):
    def test_normalize_movie_is_pure_and_coverless(self) -> None:
        conn = TraktConnector()
        item = conn._normalize_movie({"ids": {"trakt": 1, "tmdb": 5}, "title": "Arrival", "year": 2016})
        self.assertIsNotNone(item)
        assert item is not None
        self.assertIsNone(item.cover_url)  # cover deferred to the async pass
        self.assertEqual(item.release_year, 2016)

    def test_normalize_does_not_call_blocking_resolver(self) -> None:
        # The blocking sync resolver must not be invoked during normalization.
        self.assertNotIn("resolve_poster_url", inspect.getsource(TraktConnector._normalize_movie))
        self.assertNotIn("resolve_poster_url", inspect.getsource(TraktConnector._normalize_show))


class TraktPosterEnrichmentTests(unittest.TestCase):
    def test_enrich_posters_offloads_and_fills_all_covers(self) -> None:
        conn = TraktConnector()
        ids = [1, 2, 3, 4, 5]
        items = [
            conn._normalize_movie({"ids": {"trakt": i, "tmdb": i}, "title": f"t{i}", "year": 2000})
            for i in ids
        ]
        self.assertTrue(all(items), "normalization should yield an item for every non-zero id")

        calls: list[dict] = []

        def fake_resolve(**kwargs):
            calls.append(kwargs)
            return f"https://cover/{kwargs['tmdb_id']}"

        fake_settings = SimpleNamespace(tmdb_api_key="key")
        with patch.object(trakt_mod, "resolve_poster_url", fake_resolve), patch(
            "app.config.get_settings", lambda: fake_settings
        ):
            asyncio.run(conn._enrich_posters(items))

        self.assertEqual(len(calls), 5)
        self.assertTrue(all(i.cover_url == f"https://cover/{n}" for n, i in zip(ids, items)))

    def test_enrich_posters_noop_without_key(self) -> None:
        conn = TraktConnector()
        items = [conn._normalize_movie({"ids": {"trakt": 1, "tmdb": 1}, "title": "x", "year": 2000})]
        fake_settings = SimpleNamespace(tmdb_api_key="")

        def boom(**kwargs):  # must never be called when no key is configured
            raise AssertionError("resolver called without a TMDB key")

        with patch.object(trakt_mod, "resolve_poster_url", boom), patch(
            "app.config.get_settings", lambda: fake_settings
        ):
            asyncio.run(conn._enrich_posters(items))
        self.assertIsNone(items[0].cover_url)


if __name__ == "__main__":
    unittest.main()
