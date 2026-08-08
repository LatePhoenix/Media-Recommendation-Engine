"""Unit tests for the Phase 1/2 interest layer and domain separation.

These are deliberately DB-free (matching the existing suite): they exercise the
pure signal math, sort-key validation, the slug<->media mapping, and the
ranking-core behavior (hidden exclusion, saved-affinity bump) using lightweight
stand-in objects rather than a live database.
"""

from __future__ import annotations

import os
import types
import unittest
from datetime import datetime, timezone
from uuid import uuid4

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")


class InterestSignalTests(unittest.TestCase):
    def test_states_map_to_expected_signals(self) -> None:
        from app.models import ItemState
        from app.services.interest import InterestRecord, build_interest_signals

        short_id, interest_id, done_id, pass_id, hide_id = (uuid4() for _ in range(5))
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        sig = build_interest_signals(
            [
                InterestRecord(ItemState.shortlisted, short_id, genres=("Sci-Fi",), creators=("Villeneuve",)),
                InterestRecord(ItemState.interested, interest_id, genres=("Fantasy",)),
                InterestRecord(ItemState.completed, done_id, genres=("Sci-Fi",)),
                InterestRecord(ItemState.passed, pass_id, updated_at=ts),
                InterestRecord(ItemState.hidden, hide_id),
            ]
        )
        self.assertIn(hide_id, sig.hidden_ids)
        self.assertEqual(sig.passed.get(pass_id), ts)
        self.assertIn(done_id, sig.completed_ids)
        self.assertEqual(sig.soft_seen_ids, {short_id, interest_id})
        # Sci-Fi reinforced by shortlist (0.5) + completed (0.5).
        self.assertAlmostEqual(sig.genre_boosts["Sci-Fi"], 1.0)
        self.assertAlmostEqual(sig.genre_boosts["Fantasy"], 0.2)
        # Affinity surface = shortlisted + interested only.
        self.assertEqual(sig.affinity_genres, {"Sci-Fi", "Fantasy"})
        self.assertEqual(sig.affinity_creators, {"Villeneuve"})
        # Completed/passed/hidden must not seed the affinity surface.
        self.assertNotIn(hide_id, sig.affinity_genres)

    def test_saved_affinity_bounds(self) -> None:
        from app.services.interest import saved_affinity

        self.assertEqual(saved_affinity([], [], set(), set()), 0.0)
        self.assertAlmostEqual(saved_affinity(["Sci-Fi"], ["A"], {"Sci-Fi"}, {"A"}), 1.0)
        # genre overlap 1/2, no creator overlap -> 0.7 * 0.5
        self.assertAlmostEqual(saved_affinity(["Sci-Fi"], [], {"Sci-Fi", "Fantasy"}, set()), 0.35)

    def test_saved_sort_validation(self) -> None:
        from app.services.interest import VALID_SAVED_SORTS, InterestService

        for name in ("recently_added", "priority", "release_date", "score"):
            self.assertIn(name, VALID_SAVED_SORTS)
        # Unknown sort falls back to a valid clause instead of raising.
        clause = InterestService._sort_clause("bogus")
        self.assertIsInstance(clause, tuple)
        self.assertGreaterEqual(len(clause), 1)


class DomainMappingTests(unittest.TestCase):
    def test_slug_media_round_trip(self) -> None:
        from app.domains import MEDIA_TO_SLUG, SLUG_TO_MEDIA, resolve_domain
        from app.models import MediaType

        self.assertEqual(resolve_domain("movies"), MediaType.movie)
        for slug, mt in SLUG_TO_MEDIA.items():
            self.assertEqual(MEDIA_TO_SLUG[mt], slug)
        # Every media type has a slug.
        self.assertEqual(set(MEDIA_TO_SLUG), set(MediaType))

    def test_unknown_domain_is_404(self) -> None:
        from fastapi import HTTPException

        from app.domains import resolve_domain

        with self.assertRaises(HTTPException) as ctx:
            resolve_domain("widgets")
        self.assertEqual(ctx.exception.status_code, 404)


class RankingCoreTests(unittest.TestCase):
    @staticmethod
    def _item(item_id, genres):
        return types.SimpleNamespace(
            id=item_id, genres=list(genres), tags=[], creators=[], series=None, popularity=50.0
        )

    @staticmethod
    def _profile(**overrides):
        base = {
            "genre_weights": {},
            "tag_weights": {},
            "creator_weights": {},
            "liked_titles": [],
            "rated_item_ids": set(),
            "consumed_ids": set(),
            "saved_ids": set(),
            "passed": {},
            "dismiss_counts": {},
            "hidden_ids": set(),
            "affinity_genres": set(),
            "affinity_creators": set(),
        }
        base.update(overrides)
        return base

    def test_default_weights_include_interest(self) -> None:
        from app.recommender.engine import DEFAULT_WEIGHTS

        self.assertIn("interest", DEFAULT_WEIGHTS)

    def test_hidden_items_are_excluded(self) -> None:
        from app.recommender.engine import DEFAULT_WEIGHTS, score_candidates

        hidden_id, visible_id = uuid4(), uuid4()
        items = [self._item(hidden_id, ["Sci-Fi"]), self._item(visible_id, ["Sci-Fi"])]
        profile = self._profile(hidden_ids={hidden_id})
        scored = score_candidates(items, profile, dict(DEFAULT_WEIGHTS), "best_next", 14)
        ids = {c.item.id for c in scored}
        self.assertNotIn(hidden_id, ids)
        self.assertIn(visible_id, ids)

    def test_saved_affinity_adds_factor_and_reason(self) -> None:
        from app.recommender.engine import DEFAULT_WEIGHTS, score_candidates

        item_id = uuid4()
        profile = self._profile(affinity_genres={"Sci-Fi"})
        scored = score_candidates(
            [self._item(item_id, ["Sci-Fi"])], profile, dict(DEFAULT_WEIGHTS), "best_next", 14
        )
        self.assertEqual(len(scored), 1)
        factors = scored[0].factors
        self.assertGreater(factors["interest_affinity"], 0.0)
        self.assertIn("saved_related_item", factors["reasons"])


if __name__ == "__main__":
    unittest.main()
