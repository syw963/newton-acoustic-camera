"""가상 데이터 검증. 실제 교실·장비의 정확도를 평가하는 실험은 아니다."""

import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from beamforming import beamform, sound_speed_from_temperature
from data_io import load_positions, load_wav
from simulate import simulate_sources


def analytic_tones(positions, sources, rate=48000, seconds=0.12):
    """FFT로 만드는 데모와 독립인 기준 신호: 연속 시간 정현파를 직접 계산한다.

    sources = [(가로, 세로, 주파수, 진폭), ...]. 음속은 섭씨 20도 기준.
    """
    time = np.arange(round(seconds * rate)) / rate
    samples = np.zeros((len(time), len(positions)))
    for azimuth, elevation, frequency, amplitude in sources:
        az, el = math.radians(azimuth), math.radians(elevation)
        for channel, (x, y, z) in enumerate(positions):
            advance = (x * math.sin(az) * math.cos(el) + y * math.sin(el)
                       + z * math.cos(az) * math.cos(el)) / 343.42
            samples[:, channel] += amplitude * np.sin(2 * math.pi * frequency * (time + advance) + 0.2)
    return samples


class BeamformingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.positions = load_positions(ROOT / "mic_positions_example.csv")
        cls.axes = {"azimuths_deg": np.arange(-70, 71, 2), "elevations_deg": np.arange(-24, 25, 2)}

    def test_broadband_directions(self):
        for az, el in ((0, 0), (20, 10), (-32, -12), (60, -10), (-60, 20)):
            with self.subTest(azimuth=az, elevation=el):
                samples, rate = simulate_sources(self.positions, [(az, el)], seconds=0.12)
                result = beamform(samples, rate, self.positions, **self.axes)
                self.assertAlmostEqual(result.peak_direction[0], az, delta=2)
                self.assertAlmostEqual(result.peak_direction[1], el, delta=2)

    def test_independent_analytic_tones(self):
        for frequency in (1000, 2000, 4000):
            with self.subTest(frequency=frequency):
                samples = analytic_tones(self.positions, [(20, -10, frequency, 0.2)])
                result = beamform(samples, 48000, self.positions, fmin=frequency - 200, fmax=frequency + 200, **self.axes)
                self.assertEqual(result.peak_direction, (20.0, -10.0))

    def test_power_normalization_and_amplitude_scaling(self):
        samples = analytic_tones(self.positions, [(0, 0, 1500, 0.2)])
        kwargs = {"azimuths_deg": [-20, 0, 20], "elevations_deg": [0], "fmin": 1000, "fmax": 2000}
        result = beamform(samples, 48000, self.positions, **kwargs)
        half = beamform(samples * 0.5, 48000, self.positions, **kwargs)
        self.assertAlmostEqual(result.power.max(), 0.2 ** 2 / 2, delta=0.0002)
        np.testing.assert_allclose(half.power, result.power * 0.25, rtol=1e-10)
        np.testing.assert_allclose(half.relative_db, result.relative_db, atol=1e-9)

    def test_frequency_selection(self):
        samples = analytic_tones(self.positions, [(20, 0, 1500, 0.1), (-30, 0, 3000, 0.2)])
        low = beamform(samples, 48000, self.positions, fmin=1300, fmax=1700, **self.axes)
        high = beamform(samples, 48000, self.positions, fmin=2800, fmax=3200, **self.axes)
        self.assertEqual(low.peak_direction, (20, 0))
        self.assertEqual(high.peak_direction, (-30, 0))

    def test_two_independent_sources_have_two_peaks(self):
        samples, rate = simulate_sources(self.positions, [(-36, 0), (36, 0)], seconds=0.6, seed=7)
        result = beamform(samples, rate, self.positions, azimuths_deg=np.arange(-80, 81, 2), elevations_deg=[0])
        curve = result.power[0]
        peaks = [i for i in range(1, len(curve) - 1) if curve[i] > curve[i - 1] and curve[i] > curve[i + 1]]
        for truth in (-36, 36):
            self.assertTrue(any(abs(result.azimuths_deg[i] - truth) <= 4 for i in peaks))

    def test_channel_permutation_with_matching_positions(self):
        samples = analytic_tones(self.positions, [(-20, 10, 2000, 0.2)])
        order = np.random.default_rng(10).permutation(len(self.positions))
        kwargs = {"azimuths_deg": [-20, 0, 20], "elevations_deg": [-10, 0, 10]}
        original = beamform(samples, 48000, self.positions, **kwargs)
        reordered = beamform(samples[:, order], 48000, self.positions[order], **kwargs)
        np.testing.assert_allclose(original.power, reordered.power, rtol=1e-10)

    def test_spherical_wave_at_experiment_distance(self):
        source = np.array([0.55, -0.28, 1.5])
        time = np.arange(5760) / 48000
        samples = np.empty((len(time), 16))
        for channel, mic in enumerate(self.positions):
            distance = np.linalg.norm(source - mic)
            t = time - distance / 343.42
            samples[:, channel] = sum(0.03 * np.sin(2 * np.pi * f * t + f / 1000) for f in (1300, 1900, 2500, 3100)) / distance
        result = beamform(samples, 48000, self.positions, **self.axes)
        expected_az = math.degrees(math.atan2(source[0], source[2]))
        expected_el = math.degrees(math.atan2(source[1], math.hypot(source[0], source[2])))
        self.assertAlmostEqual(result.peak_direction[0], expected_az, delta=2)
        self.assertAlmostEqual(result.peak_direction[1], expected_el, delta=2)

    def test_invalid_recordings(self):
        good = analytic_tones(self.positions, [(0, 0, 2000, 0.2)])
        invalid = [np.zeros_like(good), good[:12], good[:, :2], good.astype(complex)]
        nonfinite = good.copy()
        nonfinite[0, 0] = np.nan
        invalid.append(nonfinite)
        for samples in invalid:
            with self.subTest(shape=samples.shape), self.assertRaises(ValueError):
                beamform(samples, 48000, self.positions)

    def test_invalid_geometry_and_band(self):
        samples = analytic_tones(self.positions, [(0, 0, 2000, 0.2)])
        line = self.positions.copy()
        line[:, 1] = 0
        with self.assertRaises(ValueError):
            beamform(samples, 48000, line)
        with self.assertRaises(ValueError):
            beamform(samples, 48000, self.positions, fmin=1000, fmax=25000)
        with self.assertRaises(ValueError):
            beamform(samples, 48000, self.positions, fmin=500.1, fmax=500.2)
        with self.assertRaises(ValueError):
            sound_speed_from_temperature(float("nan"))
        with self.assertRaises(ValueError):
            simulate_sources(self.positions, [(0, 0)], seconds=0.000001)

    def test_wav_round_trip_and_coordinate_order(self):
        samples = analytic_tones(self.positions, [(20, 10, 2000, 0.2)])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for subtype in ("PCM_16", "PCM_24", "FLOAT"):
                path = root / (subtype + ".wav")
                sf.write(str(path), samples, 48000, subtype=subtype, format="WAVEX")
                read, rate = load_wav(path)
                self.assertEqual(rate, 48000)
                self.assertEqual(read.shape, samples.shape)
                result = beamform(read, rate, self.positions, **self.axes)
                self.assertEqual(result.peak_direction, (20.0, 10.0))
            path = root / "positions.csv"
            rows = (ROOT / "mic_positions_example.csv").read_text().splitlines()
            path.write_text(rows[0] + "\n" + "\n".join(reversed(rows[1:])) + "\n")
            np.testing.assert_array_equal(load_positions(path), self.positions)
            path.write_text("channel,x_m,y_m,z_m\n0,0,0,0\n0,0.1,0,0\n2,0,0.1,0\n")
            with self.assertRaises(ValueError):
                load_positions(path)


if __name__ == "__main__":
    unittest.main()
