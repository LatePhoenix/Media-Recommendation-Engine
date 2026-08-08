"""Unit tests for the Phase 3 external-link resolver (DB-free pure logic)."""

from __future__ import annotations

import os
import types
import unittest

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")


class UrlBuilderTests(unittest.TestCase):
    def test_deep_links(self) -> None:
        from app.models import MediaType
        from app.services.external_links import deep_link

        self.assertEqual(deep_link("imdb", "tt0133093", MediaType.movie), "https://www.imdb.com/title/tt0133093/")
        self.assertEqual(deep_link("tmdb", "603", MediaType.movie), "https://www.themoviedb.org/movie/603")
        self.assertEqual(deep_link("tmdb", "1396", MediaType.tv), "https://www.themoviedb.org/tv/1396")
        self.assertIsNone(deep_link("imdb", "", MediaType.movie))

    def test_search_links_exist_for_core_providers(self) -> None:
        from app.services.external_links import search_link

        for provider in ("imdb", "rottentomatoes", "metacritic"):
            url = search_link(provider, "The Matrix", 1999)
            self.assertTrue(url and url.startswith("https://"))


class HarvestTests(unittest.TestCase):
    def test_harvest_imdb_and_tmdb_from_guid_blob(self) -> None:
        from app.services.external_links import harvest_keys

        refs = [
            types.SimpleNamespace(
                source="plex",
                external_id="12345",
                raw={"guid": "com.plexapp.agents.imdb://tt0133093?lang=en"},
            ),
            types.SimpleNamespace(
                source="trakt",
                external_id="999",
                raw={"ids": "tmdb://603 tvdb://1234"},
            ),
        ]
        keys = harvest_keys(refs)
        self.assertEqual(keys.get("imdb"), "tt0133093")
        self.assertEqual(keys.get("tmdb"), "603")
        self.assertEqual(keys.get("tvdb"), "1234")


class ResolveAndMergeTests(unittest.TestCase):
    def test_resolve_prefers_verified_then_search(self) -> None:
        from app.models import MediaType
        from app.services.external_links import resolve_links

        links = resolve_links(MediaType.movie, "The Matrix", 1999, {"imdb": "tt0133093"})
        by_provider = {l.provider: l for l in links}
        self.assertEqual(by_provider["imdb"].resolution_method, "imported")
        self.assertAlmostEqual(by_provider["imdb"].confidence, 1.0)
        # Providers without a harvested key fall back to a search link.
        self.assertEqual(by_provider["rottentomatoes"].resolution_method, "search")
        self.assertLess(by_provider["rottentomatoes"].confidence, 0.6)

    def test_should_write_policy(self) -> None:
        from app.services.external_links import ResolvedLink, should_write

        manual = types.SimpleNamespace(resolution_method="manual", confidence=1.0)
        verified = types.SimpleNamespace(resolution_method="imported", confidence=1.0)
        search_new = ResolvedLink("imdb", None, "u", 0.2, "search")
        verified_new = ResolvedLink("imdb", "tt1", "u", 1.0, "imported")

        # Never overwrite a manual link.
        self.assertFalse(should_write(manual, verified_new))
        # Never downgrade a verified link to a search link.
        self.assertFalse(should_write(verified, search_new))
        # Upgrade / equal-confidence refresh is allowed.
        self.assertTrue(should_write(None, search_new))
        self.assertTrue(should_write(verified, verified_new))


if __name__ == "__main__":
    unittest.main()
