"""Tests for optional FastAPI static UI mount (no DB / no app package init)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def _load_static_ui():
    """Load static_ui.py by path to avoid importing app/__init__.py (pgvector)."""
    path = Path(__file__).resolve().parents[1] / "static_ui.py"
    name = "mediarec_static_ui_under_test"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class StaticUiMountTests(unittest.TestCase):
    def test_mount_serves_index_and_spa_fallback(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        static_ui = _load_static_ui()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "index.html").write_text("<html>ok</html>", encoding="utf-8")
            assets = root / "assets"
            assets.mkdir()
            (assets / "app.js").write_text("console.log(1)", encoding="utf-8")

            app = FastAPI()

            @app.get("/health")
            def health() -> dict:
                return {"status": "ok"}

            self.assertTrue(static_ui.mount_web_ui(app, str(root)))
            client = TestClient(app)

            self.assertEqual(client.get("/health").json()["status"], "ok")
            self.assertEqual(client.get("/").text, "<html>ok</html>")
            self.assertEqual(client.get("/assets/app.js").text, "console.log(1)")
            self.assertEqual(client.get("/browse").text, "<html>ok</html>")

    def test_empty_web_dist_skips_mount(self) -> None:
        from fastapi import FastAPI

        static_ui = _load_static_ui()
        app = FastAPI()
        self.assertFalse(static_ui.mount_web_ui(app, ""))
        self.assertFalse(static_ui.mount_web_ui(app, "   "))


if __name__ == "__main__":
    unittest.main()
