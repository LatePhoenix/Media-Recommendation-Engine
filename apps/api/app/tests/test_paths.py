"""Unit tests for packaged path / env resolution (no DB required)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class PathResolutionTests(unittest.TestCase):
    def test_api_root_is_apps_api(self) -> None:
        from app.paths import resolve_api_root

        api_root = resolve_api_root()
        self.assertTrue((api_root / "alembic.ini").is_file())
        self.assertTrue((api_root / "app" / "paths.py").is_file())

    def test_shared_root_has_packages(self) -> None:
        from app.paths import ensure_sys_path, resolve_shared_root

        shared = ensure_sys_path()
        self.assertEqual(shared, resolve_shared_root())
        self.assertTrue((shared / "packages").is_dir())
        self.assertTrue((shared / "workers").is_dir())

    def test_resolve_env_files_honors_mediarec_env_file(self) -> None:
        from app.paths import resolve_env_files

        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "custom.env"
            env_path.write_text("API_SECRET_KEY=x\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"MEDIAREC_ENV_FILE": str(env_path)}, clear=False):
                files = resolve_env_files()
            self.assertIn(str(env_path.resolve()), files)

    def test_resolve_env_files_reads_programdata_layout(self) -> None:
        from app.paths import resolve_env_files

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "MediaRecommendationEngine" / "config"
            cfg.mkdir(parents=True)
            env_path = cfg / ".env"
            env_path.write_text("API_SECRET_KEY=y\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PROGRAMDATA": tmp, "MEDIAREC_ENV_FILE": ""}, clear=False):
                # Avoid accidental MEDIAREC_ENV_FILE from parent env.
                os.environ.pop("MEDIAREC_ENV_FILE", None)
                files = resolve_env_files()
            self.assertIn(str(env_path.resolve()), files)


class LaunchCliTests(unittest.TestCase):
    def test_parser_requires_command(self) -> None:
        from app.launch import build_parser

        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_parser_accepts_worker_queues(self) -> None:
        from app.launch import build_parser

        args = build_parser().parse_args(["worker", "--queues", "imports"])
        self.assertEqual(args.command, "worker")
        self.assertEqual(args.queues, ["imports"])


if __name__ == "__main__":
    unittest.main()
