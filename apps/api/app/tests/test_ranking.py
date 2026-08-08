"""Unit tests for Phase 5 ranking upgrades (DB-free where possible)."""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from uuid import uuid4

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")

# Make the repo root importable so `workers` resolves alongside `app`.
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))


def _item(genres=(), creators=(), series=None, franchise=None, popularity=50.0, tags=()):
    return types.SimpleNamespace(
        id=uuid4(),
        genres=list(genres),
        creators=list(creators),
        tags=list(tags),
        series=series,
        franchise=franchise,
        popularity=popularity,
    )


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
        "positive_ids": set(),
        "item_titles": {},
    }
    base.update(overrides)
    return base


class CooccurrenceTests(unittest.TestCase):
    def test_cosine_scores_and_min_co(self) -> None:
        from workers.recommender.jobs import cooccurrence_scores

        a, b, c = "A", "B", "C"
        user_items = {"u1": {a, b}, "u2": {a, b}, "u3": {a, c}}
        scores = cooccurrence_scores(user_items, top_k=25, min_co=2)
        # (A,B) co-occurs twice; (A,C) once -> dropped by min_co=2.
        self.assertIn((a, b), scores)
        self.assertNotIn((a, c), scores)
        self.assertAlmostEqual(scores[(a, b)], 2 / (3 * 2) ** 0.5, places=6)


class ScoreComponentTests(unittest.TestCase):
    def test_collaborative_and_availability_factors(self) -> None:
        from app.recommender.engine import DEFAULT_WEIGHTS, score_candidates

        pos = uuid4()
        item = _item(genres=["Sci-Fi"])
        collab_map = {item.id: (0.8, [pos])}
        profile = _profile(item_titles={pos: "The Matrix"})
        scored = score_candidates(
            [item],
            profile,
            dict(DEFAULT_WEIGHTS),
            "best_next",
            14,
            collab_map=collab_map,
            available_ids={item.id},
        )
        self.assertEqual(len(scored), 1)
        f = scored[0].factors
        self.assertGreater(f["collaborative"], 0.0)
        self.assertEqual(f["availability"], 1.0)
        self.assertIn("community_overlap", f["reasons"])
        self.assertIn("local_library", f["reasons"])
        self.assertEqual(f["structured"]["liked_similar_items"], ["The Matrix"])


class DiversityCapTests(unittest.TestCase):
    def test_franchise_cap_blocks_spam(self) -> None:
        from app.recommender.engine import ScoredCandidate, diversify

        cands = [
            ScoredCandidate(item=_item(franchise="Marvel", genres=["Action"]), score=1.0 - i * 0.01, factors={})
            for i in range(5)
        ]
        out = diversify(cands, limit=10, max_per_series=2)
        self.assertEqual(len(out), 2)  # only 2 of the 5 same-franchise items survive

    def test_creator_cap(self) -> None:
        from app.recommender.engine import ScoredCandidate, diversify

        cands = [
            ScoredCandidate(item=_item(creators=["Nolan"], genres=[f"g{i}"]), score=1.0 - i * 0.01, factors={})
            for i in range(6)
        ]
        out = diversify(cands, limit=10, max_per_creator=3)
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
