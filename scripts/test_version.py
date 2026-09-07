"""Version synchronization tests use disposable fixtures, never the real manifests."""

import json
import tempfile
import unittest
from pathlib import Path

from version import JSON_MANIFESTS, PYTHON_LOCK, PYTHON_MANIFEST, sync_version


class VersionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "VERSION").write_text("0.0.4\n")
        for relative in JSON_MANIFESTS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"name": "agentue", "version": "0.0.3", "private": True})
            )
        (self.root / PYTHON_MANIFEST).parent.mkdir(parents=True)
        self.toml = '[project]\nname = "agentue"\nversion = "0.0.3" # package\n\n[tool.example]\nversion = "other"\n'
        (self.root / PYTHON_MANIFEST).write_text(self.toml)
        (self.root / PYTHON_LOCK).write_text(
            '[[package]]\nname = "agentue"\nversion = "0.0.3"\n'
        )

    def test_check_reports_all_mismatches_without_writing(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(
            set(sync_version(self.root, check=True)),
            {*JSON_MANIFESTS, PYTHON_MANIFEST, PYTHON_LOCK},
        )
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_sync_preserves_other_fields_and_leaves_lock_to_uv(self):
        self.assertEqual(
            set(sync_version(self.root, check=False)),
            {*JSON_MANIFESTS, PYTHON_MANIFEST},
        )
        for relative in JSON_MANIFESTS:
            self.assertEqual(
                json.loads((self.root / relative).read_text()),
                {"name": "agentue", "version": "0.0.4", "private": True},
            )
        self.assertEqual(
            (self.root / PYTHON_MANIFEST).read_text(),
            self.toml.replace('version = "0.0.3"', 'version = "0.0.4"'),
        )
        self.assertEqual(sync_version(self.root, check=True), [PYTHON_LOCK])
        self.assertEqual(sync_version(self.root, check=False), [])

    def test_matching_versions_pass_without_rewriting(self):
        (self.root / "VERSION").write_text("0.0.3\n")
        self.assertEqual(sync_version(self.root, check=True), [])
        self.assertEqual(sync_version(self.root, check=False), [])
