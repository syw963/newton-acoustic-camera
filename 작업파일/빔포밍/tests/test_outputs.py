"""실제 실행으로 CSV·그림·공유용 메타데이터와 기존 결과 보존을 확인한다."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


class OutputTests(unittest.TestCase):
    def test_cli_exports_results_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "결과"
            command = [sys.executable, str(ROOT / "main.py"), "--demo", "--duration", "0.12",
                       "--output-dir", str(output)]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            info = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(info["input_mode"], "simulation")
            self.assertIs(info["hardware_accuracy_verified"], False)
            self.assertEqual((info["azimuth_deg"], info["elevation_deg"]), (20, 10))
            self.assertEqual(info["input_wav"], "demo.wav")
            self.assertNotIn(str(Path.home()), (output / "result.json").read_text(encoding="utf-8"))
            with (output / "summary.csv").open(encoding="utf-8-sig", newline="") as file:
                summary = list(csv.DictReader(file))
            self.assertEqual(len(summary), 1)
            self.assertEqual(float(summary[0]["azimuth_deg"]), info["azimuth_deg"])
            self.assertEqual(summary[0]["input_mode"], "simulation")
            with (output / "direction_curve.csv").open(encoding="utf-8-sig", newline="") as file:
                curve = list(csv.DictReader(file))
            self.assertEqual(len(curve), 91)
            self.assertTrue(all(float(row["elevation_deg"]) == 0 for row in curve))
            with (output / "power_map.csv").open(encoding="utf-8-sig", newline="") as file:
                points = list(csv.DictReader(file))
            self.assertEqual(len(points), 91 * 41)
            self.assertAlmostEqual(max(float(p["relative_db"]) for p in points), 0)
            with np.load(output / "power_map.npz") as data:
                expected = data["power"].ravel()
                np.testing.assert_allclose([float(p["power_uncalibrated"]) for p in points], expected)
            self.assertTrue((output / "direction.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            for name in ("summary.csv", "direction_curve.csv", "power_map.csv"):
                self.assertNotIn(b"\r\n", (output / name).read_bytes())

            before = (output / "result.json").read_bytes()
            repeat = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(repeat.returncode, 0)
            self.assertEqual((output / "result.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
