"""장치를 열지 않고 녹음 연결·실측 채널 순서·실패 시 원본 보존을 확인한다."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import soundfile as sf
from pyparsing.warnings import PyparsingDeprecationWarning

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main
import recording
from data_io import load_positions
from simulate import simulate_sources


class FakePortAudioError(Exception):
    pass


class RecordingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.positions = load_positions(ROOT / "mic_positions_uma16_usb_down.csv")
        signal, rate = simulate_sources(cls.positions, [(20, 10)], seconds=0.4)
        # 재생 시작 시각 대신 녹음 자체에서 구간을 찾는지 확인한다.
        silence = np.zeros((int(rate * 0.3), 16))
        tail = np.zeros((int(rate * 0.5), 16))
        cls.samples = np.round(np.concatenate([silence, signal, tail]) * 32768).astype(np.int16)
        cls.info = {"fs": rate, "channels": 16, "warnings": "", "play_offset_s": -123,
                    "sound": "exp3_white", "mic": "fake UMA16v2", "out": "fake headphones"}

    def audio_module(self, samples=None, info=None, channels=16):
        sio = Mock()
        sio.mic_channels = channels
        sio.mic, sio.speaker = 1, 2
        sio._name.side_effect = lambda index: f"fake device {index}"
        sio.play_and_record.return_value = (
            self.samples if samples is None else samples,
            self.info if info is None else info,
        )

        def save(data, path):
            sf.write(str(path), data, recording.FS, subtype="PCM_16")
            return path

        sio.save.side_effect = save
        module = SimpleNamespace(SoundIO=Mock(return_value=sio), load_signal=Mock(),
                                 sd=SimpleNamespace(PortAudioError=FakePortAudioError,
                                                    query_devices=Mock(return_value="fake device list")))
        return module, sio

    def run_main(self, arguments):
        # Python 3.9용 Matplotlib이 쓰는 옛 pyparsing API 경고만 제외한다.
        with warnings.catch_warnings(), patch.object(sys, "argv", ["main.py", *arguments]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            warnings.simplefilter("ignore", PyparsingDeprecationWarning)
            return main.main()

    def test_measured_channels_match_physical_row_and_column_table(self):
        # 설계 문서의 1부터 시작하는 채널표. USB 아래, 마이크 면을 마주 본 기준.
        channels = [[8, 7, 10, 9], [6, 5, 12, 11], [4, 3, 14, 13], [2, 1, 16, 15]]
        for row, y in zip(channels, [63, 21, -21, -63]):
            for channel, x in zip(row, [-63, -21, 21, 63]):
                np.testing.assert_allclose(self.positions[channel - 1], [x / 1000, y / 1000, 0])

    def test_record_to_direction_and_exports_without_hardware(self):
        module, sio = self.audio_module()
        with tempfile.TemporaryDirectory() as folder, patch.object(recording, "team_audio_module", return_value=module):
            output = Path(folder) / "measurement"
            code = self.run_main(["--record", "--out", "2", "--output-dir", str(output)])
            self.assertEqual(code, 0)
            sio.play_and_record.assert_called_once_with("exp3_white", "A", volume=0.3, pre_roll=0.3, post_roll=0.5)
            module.SoundIO.assert_called_once_with(mic=None, speaker="2")
            info = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(info["input_mode"], "recording")
            self.assertEqual(info["mic_positions_file"], "mic_positions_uma16_usb_down.csv")
            self.assertEqual((info["azimuth_deg"], info["elevation_deg"]), (20, 10))
            self.assertIs(info["hardware_accuracy_verified"], False)
            self.assertAlmostEqual(info["start_seconds"], 0.3)
            self.assertAlmostEqual(info["duration_seconds"], 0.4)
            self.assertTrue(info["recording"]["quality"]["ok"])
            saved, rate = sf.read(str(output / "recording.wav"), dtype="int16")
            np.testing.assert_array_equal(saved, self.samples)
            self.assertEqual(rate, 48000)
            for name in ["recording_info.json", "summary.csv", "direction_curve.csv", "power_map.csv", "power_map.npz"]:
                self.assertTrue((output / name).is_file(), name)
            self.assertTrue((output / "direction.png").read_bytes().startswith(b"\x89PNG"))

    def test_bad_capture_preserves_wav_and_stops_before_direction(self):
        clipped = self.samples.copy()
        clipped[20000, 0] = 32767
        cases = [
            (self.samples, {**self.info, "warnings": "input overflow"}),
            (clipped, self.info),
            (np.zeros_like(self.samples), self.info),
            (self.samples, {**self.info, "fs": 44100}),
            (np.random.default_rng(3).integers(-1000, 1000, self.samples.shape, dtype=np.int16), self.info),
        ]
        for samples, info in cases:
            with self.subTest(warnings=info["warnings"], fs=info["fs"], peak=int(samples.max())), \
                    tempfile.TemporaryDirectory() as folder:
                module, _ = self.audio_module(samples, info)
                output = Path(folder) / "bad"
                with patch.object(recording, "team_audio_module", return_value=module):
                    self.assertEqual(self.run_main(["--record", "--output-dir", str(output)]), 1)
                self.assertTrue((output / "recording.wav").is_file())
                metadata = json.loads((output / "recording_info.json").read_text(encoding="utf-8"))
                self.assertFalse(metadata["quality"]["ok"])
                self.assertFalse((output / "direction.png").exists())
                self.assertFalse((output / "result.json").exists())

    def test_non_array_microphone_is_refused_before_playback(self):
        module, sio = self.audio_module(channels=2)
        with tempfile.TemporaryDirectory() as folder, patch.object(recording, "team_audio_module", return_value=module):
            self.assertEqual(self.run_main(["--record", "--output-dir", str(Path(folder) / "wrong")]), 1)
        sio.play_and_record.assert_not_called()

    def test_audio_device_error_is_reported_without_traceback(self):
        module, sio = self.audio_module()
        sio.play_and_record.side_effect = FakePortAudioError("device unavailable")
        with tempfile.TemporaryDirectory() as folder, patch.object(recording, "team_audio_module", return_value=module):
            self.assertEqual(self.run_main(["--record", "--output-dir", str(Path(folder) / "error")]), 1)

    def test_devices_lists_without_recording_or_output_folder(self):
        module, sio = self.audio_module()
        with patch.object(recording, "team_audio_module", return_value=module):
            self.assertEqual(self.run_main(["--devices"]), 0)
        module.sd.query_devices.assert_called_once_with()
        module.SoundIO.assert_not_called()
        sio.play_and_record.assert_not_called()

    def test_existing_wav_uses_measured_positions_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / "recording.wav"
            sf.write(str(wav), self.samples, recording.FS, subtype="PCM_16")
            output = Path(folder) / "analysis"
            self.assertEqual(self.run_main(["--wav", str(wav), "--start", "0.3", "--duration", "0.4",
                                            "--output-dir", str(output)]), 0)
            info = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(info["input_mode"], "file")
            self.assertEqual((info["azimuth_deg"], info["elevation_deg"]), (20, 10))
            self.assertNotIn("recording", info)


if __name__ == "__main__":
    unittest.main()
