"""Tests for the independent AURA release verifier profiles."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aura_release_verify import REQUIRED, SKILL_REQUIRED, verify_root, verify_skill_root, verify_skill_zip, verify_zip


class ReleaseVerifierTests(unittest.TestCase):
    def _make_skill_root(self, directory: Path) -> Path:
        root = directory / "skill"
        for relative in SKILL_REQUIRED:
            if relative == "SHA256SUMS.txt":
                continue
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("content\n", encoding="utf-8")
        entries = []
        for relative in SKILL_REQUIRED:
            if relative == "SHA256SUMS.txt":
                continue
            path = root / relative
            entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
        (root / "SHA256SUMS.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
        return root

    def test_skill_root_accepts_clean_hashed_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            checks = verify_skill_root(self._make_skill_root(Path(directory)), require_hashes=True)
            self.assertTrue(all(check["ok"] for check in checks), checks)

    def test_full_windows_root_accepts_required_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "aura"
            for relative in REQUIRED:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix.lower() == ".bat":
                    path.write_bytes(b"@echo off\r\n")
                else:
                    path.write_text("content\n", encoding="utf-8")
            checks = verify_root(root)
            self.assertTrue(all(check["ok"] for check in checks), checks)

    def test_full_windows_zip_requires_complete_hashed_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "aura"
            for relative in REQUIRED:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix.lower() == ".bat":
                    path.write_bytes(b"@echo off\r\n")
                else:
                    path.write_text("content\n", encoding="utf-8")
            entries = [f"{hashlib.sha256((root / relative).read_bytes()).hexdigest()}  {relative}" for relative in REQUIRED]
            (root / "SHA256SUMS.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
            archive_path = Path(directory) / "aura.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in root.rglob("*"):
                    if path.is_file():
                        archive.write(path, Path("aura") / path.relative_to(root))
            result = verify_zip(archive_path)
            self.assertTrue(result["ok"], result)

    def test_full_windows_zip_rejects_bat_only_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "incomplete.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("aura/AURA_INSTALAR_E_INICIAR_TUDO.bat", "@echo off\r\n")
            result = verify_zip(archive_path)
            self.assertFalse(result["ok"])
            self.assertIn("PACKAGE_RELEASE.txt", result["detail"]["missing"])

    def test_skill_zip_accepts_clean_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_skill_root(Path(directory))
            archive_path = Path(directory) / "skill.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in root.rglob("*"):
                    if path.is_file():
                        archive.write(path, Path("skill") / path.relative_to(root))
            result = verify_skill_zip(archive_path)
            self.assertTrue(result["ok"], result)

    def test_skill_root_rejects_unlisted_file_in_strict_hash_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_skill_root(Path(directory))
            (root / "unlisted.txt").write_text("not covered", encoding="utf-8")
            checks = verify_skill_root(root, require_hashes=True)
            hashes = next(check for check in checks if check["name"] == "sha256")
            self.assertFalse(hashes["ok"])
            self.assertIn("unlisted:unlisted.txt", hashes["detail"])

    def test_skill_root_rejects_forbidden_transient_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_skill_root(Path(directory))
            (root / "runtime.db").write_bytes(b"must not ship")
            checks = verify_skill_root(root, require_hashes=True)
            clean = next(check for check in checks if check["name"] == "clean_distribution")
            self.assertFalse(clean["ok"])
            self.assertIn("runtime.db", clean["detail"])

    def test_skill_root_rejects_sqlite_sidecar_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_skill_root(Path(directory))
            (root / "runtime.sqlite-wal").write_bytes(b"must not ship")
            checks = verify_skill_root(root, require_hashes=True)
            clean = next(check for check in checks if check["name"] == "clean_distribution")
            self.assertFalse(clean["ok"])
            self.assertIn("runtime.sqlite-wal", clean["detail"])

    def test_hash_profile_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_skill_root(Path(directory))
            sums = root / "SHA256SUMS.txt"
            sums.write_text(sums.read_text(encoding="utf-8") + ("0" * 64) + "  ../outside.txt\n", encoding="utf-8")
            checks = verify_skill_root(root, require_hashes=True)
            hashes = next(check for check in checks if check["name"] == "sha256")
            self.assertFalse(hashes["ok"])
            self.assertIn("unsafe_path:../outside.txt", hashes["detail"])

    def test_skill_zip_rejects_tampered_hashed_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._make_skill_root(Path(directory))
            archive_path = Path(directory) / "tampered.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for path in root.rglob("*"):
                    if path.is_file():
                        payload = b"tampered\n" if path.name == "SKILL.md" else path.read_bytes()
                        archive.writestr((Path("skill") / path.relative_to(root)).as_posix(), payload)
            result = verify_skill_zip(archive_path)
            self.assertFalse(result["ok"])
            self.assertIn("mismatch:SKILL.md", result["detail"]["sha256"])

    def test_skill_zip_rejects_path_traversal_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "traversal.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("skill/SKILL.md", "skill")
                archive.writestr("skill/SHA256SUMS.txt", "hashes")
                archive.writestr("skill/scripts/aura_admin_core.py", "core")
                archive.writestr("skill/../outside.txt", "bad")
            result = verify_skill_zip(archive_path)
            self.assertFalse(result["ok"])
            self.assertIn("skill/../outside.txt", result["detail"]["unsafe_paths"])

    def test_skill_zip_requires_core_files_and_rejects_transient_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "skill.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("skill/SKILL.md", "skill")
                archive.writestr("skill/SHA256SUMS.txt", "hashes")
                archive.writestr("skill/scripts/aura_admin_core.py", "core")
                archive.writestr("skill/runtime.db", "bad")
            result = verify_skill_zip(archive_path)
            self.assertFalse(result["ok"])
            self.assertIn("skill/runtime.db", result["detail"]["forbidden"])


if __name__ == "__main__":
    unittest.main()
