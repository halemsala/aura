from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from video_pipeline import VideoPipeline  # noqa: E402


class VideoPipelineTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        base = Path(self.td.name)
        self.pipe = VideoPipeline(base / "work", base / "exports")

    def tearDown(self):
        self.td.cleanup()

    def test_trim_plan_valid(self):
        p = self.pipe.plan_trim("/tmp/fake_in.mp4", "out_trim.mp4", "00:00:01", "00:00:02")
        self.assertEqual(p.op, "trim")
        self.assertIsNotNone(p.ffmpeg_cmd)
        self.assertFalse(p.overwrite_source)

    def test_concat_plan(self):
        p = self.pipe.plan_concat(["a.mp4", "b.mp4"], "out_cat.mp4")
        self.assertEqual(p.op, "concat")

    def test_extract_audio_plan(self):
        p = self.pipe.plan_extract_audio("a.mp4", "out.aac")
        self.assertEqual(p.op, "extract_audio")

    def test_subtitles_plan(self):
        p = self.pipe.plan_subtitles("a.mp4", "a.srt", "out_sub.mp4")
        self.assertEqual(p.op, "subtitles")

    def test_dry_run_without_approval(self):
        p = self.pipe.plan_trim("a.mp4", "o.mp4", "0", "1")
        r = self.pipe.execute(p, execute=False)
        self.assertEqual(r["status"], "DRY_RUN")
        self.assertFalse(r["executed"])

    def test_execute_blocked_without_env(self):
        os.environ.pop("AURA_VIDEO_EXECUTION_APPROVED", None)
        p = self.pipe.plan_trim("a.mp4", "o.mp4", "0", "1")
        r = self.pipe.execute(p, execute=True)
        self.assertEqual(r["status"], "DRY_RUN")
        self.assertFalse(r["executed"])

    def test_blocks_existing_output(self):
        out = self.pipe.export_dir / "exists.mp4"
        out.write_bytes(b"x")
        p = self.pipe.plan_trim("a.mp4", "exists.mp4", "0", "1")
        errs = self.pipe.validate(p)
        self.assertTrue(any("exists" in e for e in errs))


if __name__ == "__main__":
    unittest.main()
