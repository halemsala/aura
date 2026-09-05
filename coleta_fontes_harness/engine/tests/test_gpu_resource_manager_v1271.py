from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.gpu_resource_manager import GPUResourceManager


class GPUResourceManagerV1271Tests(unittest.TestCase):
    def test_cpu_fallback_when_no_vram_is_detected(self) -> None:
        manager = GPUResourceManager(lock_path=str(Path(tempfile.gettempdir()) / "aura-test-gpu.lock"))
        manager.vram_total_gb = 0.0
        manager.vram_safe_limit_gb = 0.0
        with patch("engine.gpu_resource_manager.resolve_cuda_device", return_value="cpu"):
            self.assertEqual(manager.get_best_device(1.5), "cpu")
            self.assertEqual(manager.health()["status"], "NO_GPU")

    def test_safe_limit_and_pressure_decision(self) -> None:
        manager = GPUResourceManager(safe_fraction=0.85, lock_path=str(Path(tempfile.gettempdir()) / "aura-test-gpu.lock"))
        manager.vram_total_gb = 6.0
        manager.vram_safe_limit_gb = 5.1
        with patch.object(manager, "get_current_vram_usage_gb", return_value=2.0):
            self.assertTrue(manager.is_safe_to_infer(1.5))
            self.assertFalse(manager.is_safe_to_infer(3.2))

    def test_inference_slot_releases_after_exception(self) -> None:
        lock_path = Path(tempfile.gettempdir()) / "aura-test-gpu-slot.lock"
        manager = GPUResourceManager(lock_path=str(lock_path))
        manager.vram_total_gb = 0.0
        manager.vram_safe_limit_gb = 0.0
        with self.assertRaises(RuntimeError):
            with manager.inference_slot(1.0) as device:
                self.assertEqual(device, "cpu")
                raise RuntimeError("fixture")
        self.assertFalse(manager._thread_lock.locked())
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
