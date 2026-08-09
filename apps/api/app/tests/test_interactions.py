"""DB-free tests for interaction item-existence guard (M-1), the global IntegrityError
handler (Q-1), and the register bootstrap/duplicate hardening (M-2)."""

from __future__ import annotations

import inspect
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

os.environ.setdefault(
    "API_SECRET_KEY", "test-secret-key-that-is-definitely-long-enough-1234567890"
)
os.environ.setdefault("CREDENTIALS_FERNET_KEY", "vyErqHdYcVkJLcxYI04YW5JVAuRBAu3ad58GfOzMf3k=")


class CreateInteractionGuardTests(unittest.TestCase):
    """M-1: an unknown item_id must yield a 404, not a 500 on FK violation."""

    def _payload(self):
        from app.models import InteractionType
        from app.schemas import InteractionCreate

        return InteractionCreate(
            item_id=uuid4(),
            interaction_type=InteractionType.rate,
            rating_label="Liked it",
        )

    def test_rejects_unknown_item_with_404(self) -> None:
        from fastapi import HTTPException

        from app.routers.interactions import create_interaction

        db = MagicMock()
        db.get.return_value = None  # item does not exist
        user = SimpleNamespace(id=uuid4())

        with self.assertRaises(HTTPException) as ctx:
            create_interaction(db, user, self._payload())
        self.assertEqual(ctx.exception.status_code, 404)
        db.add.assert_not_called()

    def test_accepts_known_item(self) -> None:
        from app.routers.interactions import create_interaction

        item_id = uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(id=item_id)  # item exists
        user = SimpleNamespace(id=uuid4())

        row = create_interaction(db, user, self._payload())
        self.assertIsNotNone(row)
        db.add.assert_called_once()


class IntegrityErrorHandlerTests(unittest.TestCase):
    """Q-1: the app registers a global IntegrityError -> 409 handler (no bare 500s)."""

    def test_handler_registered(self) -> None:
        from sqlalchemy.exc import IntegrityError

        from app.main import app

        self.assertIn(IntegrityError, app.exception_handlers)


class ManualLinkSchemeTests(unittest.TestCase):
    """L-2: manual external links must be http(s); reject stored-XSS schemes."""

    def test_rejects_javascript_scheme(self) -> None:
        from pydantic import ValidationError

        from app.schemas import ManualLinkIn

        with self.assertRaises(ValidationError):
            ManualLinkIn(provider="imdb", external_url="javascript:alert(1)")

    def test_accepts_https(self) -> None:
        from app.schemas import ManualLinkIn

        link = ManualLinkIn(provider="imdb", external_url="https://www.imdb.com/title/tt0000001/")
        self.assertEqual(link.provider, "imdb")


class RegisterHardeningTests(unittest.TestCase):
    """M-2: bootstrap race serialized + duplicate collision returns a clean 400."""

    def test_register_source_hardening(self) -> None:
        from app.routers import auth as auth_mod

        src = inspect.getsource(auth_mod.register)
        # First-user admin bootstrap is serialized against concurrent registrations.
        self.assertIn("pg_advisory_xact_lock", src)
        # A duplicate that slips past the pre-check is caught, not surfaced as a 500.
        self.assertIn("except IntegrityError", src)
        self.assertIn("db.rollback()", src)


if __name__ == "__main__":
    unittest.main()
