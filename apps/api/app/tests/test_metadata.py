"""Unit tests for Phase 4 normalization (the canonical-identity / dedup backbone).

Pure and DB-free: exercises the text normalization that collapses title/name/tag
variants into stable keys.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")


class NormalizeTitleTests(unittest.TestCase):
    def test_article_and_punctuation_variants_collapse(self) -> None:
        from app.services.normalize import normalize_title

        canonical = normalize_title("The Matrix")
        self.assertEqual(canonical, "matrix")
        for variant in ("Matrix, The", "matrix", "  The   Matrix!  ", "THE MATRIX"):
            self.assertEqual(normalize_title(variant), canonical, variant)

    def test_accents_and_colon_variants(self) -> None:
        from app.services.normalize import normalize_title

        self.assertEqual(
            normalize_title("Amélie"), normalize_title("Amelie")
        )
        self.assertEqual(
            normalize_title("Spider-Man: No Way Home"),
            normalize_title("Spider Man No Way Home"),
        )

    def test_distinct_titles_stay_distinct(self) -> None:
        from app.services.normalize import normalize_title

        self.assertNotEqual(normalize_title("Dune"), normalize_title("Dune Part Two"))

    def test_empty(self) -> None:
        from app.services.normalize import normalize_title

        self.assertEqual(normalize_title(None), "")
        self.assertEqual(normalize_title("   "), "")


class NormalizeNameAndSlugTests(unittest.TestCase):
    def test_name_normalization(self) -> None:
        from app.services.normalize import normalize_name

        self.assertEqual(normalize_name("Denis Villeneuve"), "denis villeneuve")
        self.assertEqual(normalize_name("BONG Joon-ho"), normalize_name("Bong Joon Ho"))

    def test_slugify(self) -> None:
        from app.services.normalize import slugify

        self.assertEqual(slugify("Science Fiction"), "science-fiction")
        self.assertEqual(slugify("Sci-Fi!"), "sci-fi")


if __name__ == "__main__":
    unittest.main()
