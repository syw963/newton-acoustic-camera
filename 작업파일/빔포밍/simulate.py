"""장비 없이 방향 계산을 시험할 가상 동시 녹음을 만든다.

실내 반사음이 없는 이상적인 평면파이다. 정답은 이곳에서 녹음 생성에만 사용한다.
"""

import numpy as np

from beamforming import direction_vectors, sound_speed_from_temperature


def simulate_sources(positions, sources, *, sample_rate=48000, seconds=0.5,
                     temperature_c=20.0, noise_std=0.003, seed=42):
    """sources 예: [(가로 각도, 세로 각도), ...]. 음원마다 독립인 대역 잡음을 만든다."""
    positions = np.asarray(positions, dtype=float)
    if not np.isfinite(seconds) or seconds <= 0 or not sources:
        raise ValueError("가상 녹음 길이는 양수이고 음원이 한 개 이상 있어야 해.")
    if not np.isfinite(noise_std) or noise_std < 0:
        raise ValueError("잡음 크기는 0 이상의 유한한 숫자여야 해.")
    speed = sound_speed_from_temperature(temperature_c)
    rng = np.random.default_rng(seed)
    if not isinstance(sample_rate, (int, np.integer)) or sample_rate < 8000:
        raise ValueError("가상 녹음의 샘플링 주파수는 8000Hz 이상의 정수여야 해.")
    count = int(seconds * sample_rate)
    if count < 64:
        raise ValueError("가상 녹음이 너무 짧아. 64개 이상의 샘플이 필요해.")
    frequencies = np.fft.rfftfreq(count, d=1 / sample_rate)
    samples = np.zeros((count, len(positions)))
    for azimuth, elevation in sources:
        if not np.isfinite(azimuth) or not np.isfinite(elevation) or abs(azimuth) > 90 or abs(elevation) >= 90:
            raise ValueError("가상 음원은 앞쪽 방향의 유한한 각도여야 해.")
        source = rng.standard_normal(count)
        spectrum = np.fft.rfft(source)
        spectrum[(frequencies < 1800) | (frequencies > 3500)] = 0
        source_rms = np.sqrt(np.mean(np.fft.irfft(spectrum, n=count) ** 2))
        if source_rms == 0:
            raise ValueError("가상 녹음의 샘플링 주파수나 길이가 너무 작아.")
        spectrum *= 0.08 / source_rms
        unit = direction_vectors(azimuth, elevation)
        for channel, mic in enumerate(positions):
            # 마이크가 음원 쪽으로 가까울수록 먼저 도착한다.
            advance_seconds = float(mic @ unit / speed)
            shifted = spectrum * np.exp(2j * np.pi * frequencies * advance_seconds)
            samples[:, channel] += np.fft.irfft(shifted, n=count)
    samples += rng.normal(0, noise_std, samples.shape)
    return samples, sample_rate
