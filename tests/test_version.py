import importlib
from importlib.metadata import PackageNotFoundError
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import entropy
from scripts.check_version import check_versions


class VersionCheckTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "packaging" / "arch").mkdir(parents=True)
        (self.root / "debian").mkdir()
        (self.root / "pyproject.toml").write_text(
            '[project]\nname = "entropy-player"\nversion = "0.1.2"\n',
            encoding="utf-8",
        )
        (self.root / "packaging" / "arch" / "PKGBUILD").write_text(
            "pkgname=entropy-player\npkgver=0.1.2\n",
            encoding="utf-8",
        )
        (self.root / "debian" / "changelog").write_text(
            "entropy-player (0.1.2-1) unstable; urgency=medium\n",
            encoding="utf-8",
        )

    def tearDown(self):
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.root.rmdir()

    def test_matching_versions_pass(self):
        self.assertEqual(check_versions(self.root), "0.1.2")

    def test_each_distribution_version_mismatch_fails(self):
        files_and_contents = (
            (
                self.root / "pyproject.toml",
                '[project]\nname = "entropy-player"\nversion = "0.1.3"\n',
            ),
            (
                self.root / "packaging" / "arch" / "PKGBUILD",
                "pkgname=entropy-player\npkgver=0.1.3\n",
            ),
            (
                self.root / "debian" / "changelog",
                "entropy-player (0.1.3-1) unstable; urgency=medium\n",
            ),
        )
        originals = {path: path.read_text(encoding="utf-8") for path, _ in files_and_contents}
        for changed_path, changed_contents in files_and_contents:
            with self.subTest(file=changed_path):
                changed_path.write_text(changed_contents, encoding="utf-8")
                with self.assertRaises(ValueError):
                    check_versions(self.root)
                changed_path.write_text(originals[changed_path], encoding="utf-8")

    def test_source_checkout_has_local_version_fallback(self):
        try:
            with patch(
                "importlib.metadata.version",
                side_effect=PackageNotFoundError("entropy-player"),
            ):
                importlib.reload(entropy)
                self.assertEqual(entropy.__version__, "0+local")
        finally:
            importlib.reload(entropy)

    def test_module_cli_can_show_version_from_checkout(self):
        result = subprocess.run(
            [sys.executable, "-m", "entropy", "--version"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn(f"Entropy Player {entropy.__version__}", result.stdout)


if __name__ == "__main__":
    unittest.main()
