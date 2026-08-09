from __future__ import annotations

import unittest

from workers.importers.poster_enrichment import extract_provider_ids


class PosterEnrichmentIdsTest(unittest.TestCase):
    def test_trakt_ids(self) -> None:
        ids = extract_provider_ids({"ids": {"tmdb": 123, "imdb": "tt0111161"}})
        self.assertEqual(ids["tmdb"], "123")
        self.assertEqual(ids["imdb"], "tt0111161")

    def test_plex_guids(self) -> None:
        ids = extract_provider_ids({"guids": ["tmdb://550", "imdb://tt0137523"]})
        self.assertEqual(ids["tmdb"], "550")
        self.assertEqual(ids["imdb"], "tt0137523")

    def test_jellyfin_provider_ids(self) -> None:
        ids = extract_provider_ids({"ProviderIds": {"Tmdb": "278", "Imdb": "tt0111161"}})
        self.assertEqual(ids["tmdb"], "278")
        self.assertEqual(ids["imdb"], "tt0111161")


if __name__ == "__main__":
    unittest.main()
