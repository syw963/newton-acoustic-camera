"""가상 데이터로 방향의 부호와 입력 파일 처리를 확인한다. 장비 검증은 아니다."""

import math
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import locate_sound as sound


class DirectionTests(unittest.TestCase):
    def setUp(self):
        self.positions = sound.read_positions(sound.HERE / "mic_positions_example.csv")

    def test_directions_from_independent_pulses(self):
        # 데모의 정현파 합성과 다른 방식: 시간차를 준 두 개의 짧은 펄스.
        rate = 16000
        for azimuth, elevation in ((0, 0), (25, 15), (-35, -20), (55, -10)):
            with self.subTest(azimuth=azimuth, elevation=elevation):
                az, el = math.radians(azimuth), math.radians(elevation)
                ux, uy = math.sin(az) * math.cos(el), math.sin(el)
                channels = []
                for x, y, _ in self.positions:
                    delay = -(x * ux + y * uy) / sound.SOUND_SPEED
                    values = []
                    for i in range(1920):
                        t = i / rate - delay
                        values.append(math.exp(-((t - 0.02) / 0.0002) ** 2)
                                      - 0.6 * math.exp(-((t - 0.03) / 0.0003) ** 2))
                    channels.append(values)
                result = sound.estimate_direction(channels, rate, self.positions)
                self.assertAlmostEqual(result["azimuth_deg"], azimuth, delta=0.5)
                self.assertAlmostEqual(result["elevation_deg"], elevation, delta=0.5)

    def test_silence_and_channel_mismatch(self):
        with self.assertRaisesRegex(ValueError, "무음"):
            sound.estimate_direction([[0.0] * 1024] * 16, 48000, self.positions)
        with self.assertRaisesRegex(ValueError, "채널 수"):
            sound.estimate_direction([[0.0] * 1024] * 2, 48000, self.positions)

    def test_collinear_positions(self):
        channel = [math.sin(i / 10) for i in range(1024)]
        with self.assertRaisesRegex(ValueError, "정보가 부족"):
            sound.estimate_direction([channel] * 3, 48000, [(0, 0, 0), (0.04, 0, 0), (0.08, 0, 0)])

    def test_wave_formats_and_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.wav"
            for bits, kind, extended in ((16, 1, False), (24, 1, True), (32, 1, False), (32, 3, True)):
                with self.subTest(bits=bits, kind=kind):
                    width = bits // 8
                    fmt = struct.pack("<HHIIHH", 65534 if extended else kind, 4, 48000,
                                      48000 * 4 * width, 4 * width, bits)
                    if extended:
                        fmt += struct.pack("<HHII", 22, bits, 0, kind)
                        fmt += bytes.fromhex("00001000800000aa00389b71")
                    sample = struct.pack("<f", 0.25) if kind == 3 else int(2 ** (bits - 3)).to_bytes(width, "little", signed=True)
                    raw = sample * 600 * 4
                    body = b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(raw)) + raw
                    recording = b"RIFF" + struct.pack("<I", len(body)) + body
                    path.write_bytes(recording)
                    channels, rate = sound.read_recording(path)
                    self.assertEqual(rate, 48000)
                    self.assertEqual(len(channels), 4)
                    self.assertEqual(len(channels[0]), 600)
                    self.assertAlmostEqual(channels[0][0], 0.25)
                    path.write_bytes(recording[:-10])
                    with self.assertRaisesRegex(ValueError, "잘렸어"):
                        sound.read_recording(path)

    def test_plot_coordinate_and_demo_label(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "plot.svg"
            result = {"azimuth_deg": 20, "elevation_deg": 10}
            sound.save_plot(path, result, result)
            root = ET.parse(path).getroot()
            dots = root.findall("{http://www.w3.org/2000/svg}g/{http://www.w3.org/2000/svg}circle")
            self.assertEqual(float(dots[-1].attrib["cx"]), 466)
            self.assertEqual(float(dots[-1].attrib["cy"]), 295)
            self.assertIn("실제 장비의 측정 결과가 아님", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
