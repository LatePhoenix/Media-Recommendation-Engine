"""Unit tests for merge_items interaction survival (DB-free logic via mocks)."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")


class MergeItemsContractTests(unittest.TestCase):
    def test_merge_repoints_user_interaction(self) -> None:
        """Ensure UserInteraction is included in the plain-repoint model list."""
        import inspect

        from app.services import metadata as meta_mod

        src = inspect.getsource(meta_mod.MetadataNormalizationService.merge_items)
        self.assertIn("UserInteraction", src)
        self.assertIn("ItemExternalRef", src)

    def test_merge_same_id_noop(self) -> None:
        from app.services.metadata import MetadataNormalizationService

        db = MagicMock()
        svc = MetadataNormalizationService(db)
        item = SimpleNamespace(id=uuid4())
        self.assertIs(svc.merge_items(item, item), item)
        db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
