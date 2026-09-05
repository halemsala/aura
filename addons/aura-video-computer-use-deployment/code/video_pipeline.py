"""Pipeline determinístico de vídeo — plan/dry-run only until dual approval."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

Op = Literal["trim", "concat", "extract_audio", "subtitles"]


@dataclass
class VideoPlan:
    op: Op
    sources: list[str]
    output: str
    params: dict[str, Any]
    mode: str = "dry_run"
    overwrite_source: bool = False
    ffmpeg_cmd: list[str] | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


class VideoPipeline:
    """Sem execução a menos que --execute e AURA_VIDEO_EXECUTION_APPROVED=true."""

    def __init__(self, work_dir: str | Path, export_dir: str | Path) -> None:
        self.work_dir = Path(work_dir)
        self.export_dir = Path(export_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def plan_trim(self, src: str, output_name: str, start: str, duration: str) -> VideoPlan:
        out = str(self.export_dir / output_name)
        cmd = [
            "ffmpeg", "-y", "-ss", start, "-i", src, "-t", duration,
            "-c", "copy", out,
        ]
        return VideoPlan("trim", [src], out, {"start": start, "duration": duration}, ffmpeg_cmd=cmd)

    def plan_concat(self, sources: list[str], output_name: str) -> VideoPlan:
        out = str(self.export_dir / output_name)
        # concat demuxer needs list file — plan only
        list_file = str(self.work_dir / "concat_list.txt")
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", out]
        return VideoPlan("concat", list(sources), out, {"list_file": list_file}, ffmpeg_cmd=cmd)

    def plan_extract_audio(self, src: str, output_name: str) -> VideoPlan:
        out = str(self.export_dir / output_name)
        cmd = ["ffmpeg", "-y", "-i", src, "-vn", "-acodec", "copy", out]
        return VideoPlan("extract_audio", [src], out, {}, ffmpeg_cmd=cmd)

    def plan_subtitles(self, src: str, srt: str, output_name: str) -> VideoPlan:
        out = str(self.export_dir / output_name)
        # subtitles filter may need re-encode — still plan-only here
        cmd = ["ffmpeg", "-y", "-i", src, "-vf", f"subtitles={srt}", out]
        return VideoPlan("subtitles", [src, srt], out, {"srt": srt}, ffmpeg_cmd=cmd)

    def validate(self, plan: VideoPlan) -> list[str]:
        errors: list[str] = []
        if plan.overwrite_source:
            errors.append("overwrite_source forbidden")
        out = Path(plan.output)
        if out.exists():
            errors.append(f"output already exists: {out}")
        for s in plan.sources:
            # sources may be synthetic in dry-run validation of structure
            if ".." in Path(s).parts:
                errors.append(f"path traversal blocked: {s}")
        if plan.output in plan.sources:
            errors.append("output must not equal source")
        return errors

    def execute(self, plan: VideoPlan, *, execute: bool = False) -> dict[str, Any]:
        errs = self.validate(plan)
        approved = os.environ.get("AURA_VIDEO_EXECUTION_APPROVED", "").lower() in {"1", "true", "yes"}
        if not execute or not approved:
            return {
                "status": "DRY_RUN",
                "executed": False,
                "plan": asdict(plan),
                "validation_errors": errs,
                "require": ["--execute", "AURA_VIDEO_EXECUTION_APPROVED=true"],
            }
        if errs:
            return {"status": "BLOCKED", "executed": False, "errors": errs}
        if not plan.ffmpeg_cmd:
            return {"status": "BLOCKED", "executed": False, "errors": ["no ffmpeg_cmd"]}
        # still refuse if any source is missing
        for s in plan.sources:
            if plan.op == "concat" and s == plan.params.get("list_file"):
                continue
            if plan.op == "concat":
                break
            if not Path(s).exists():
                return {"status": "BLOCKED", "executed": False, "errors": [f"missing source {s}"]}
        proc = subprocess.run(plan.ffmpeg_cmd, capture_output=True, text=True)
        return {
            "status": "OK" if proc.returncode == 0 else "FAIL",
            "executed": proc.returncode == 0,
            "returncode": proc.returncode,
            "stderr_tail": (proc.stderr or "")[-500:],
        }
