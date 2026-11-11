"""지연-합 빔포밍: 녹음과 마이크 위치만 받아 방향별 소리 세기를 구한다.

좌표: x=오른쪽, y=위쪽, z=앞쪽. samples의 모양은 (시간 샘플 수, 마이크 수).
이 파일은 파일 읽기, 그림 그리기, 아두이노 제어를 하지 않는다.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class BeamformingResult:
    azimuths_deg: np.ndarray
    elevations_deg: np.ndarray
    power: np.ndarray  # 행=세로 각도, 열=가로 각도. 보정 전 평균 제곱값.
    frequencies_hz: np.ndarray
    frame_count: int
    sample_rate: int
    block_size: int
    sound_speed: float

    @property
    def peak_direction(self):
        """가장 강한 칸의 (가로 각도, 세로 각도). 정확도나 음원 개수는 뜻하지 않는다."""
        row, column = np.unravel_index(np.argmax(self.power), self.power.shape)
        return float(self.azimuths_deg[column]), float(self.elevations_deg[row])

    @property
    def relative_db(self):
        """이번 지도의 최대값을 0 dB로 놓는다. 실제 소음도 dB SPL이 아니다."""
        return 10 * np.log10(np.maximum(self.power / self.power.max(), 1e-12))


def sound_speed_from_temperature(temperature_c):
    """계획서의 기온 보정식. 섭씨 → m/s."""
    if not np.isfinite(temperature_c) or not -40 <= temperature_c <= 60:
        raise ValueError("기온은 -40~60°C 범위의 유한한 숫자로 입력해 줘.")
    return 331.3 + 0.606 * float(temperature_c)


def direction_vectors(azimuths_deg, elevations_deg):
    """각도를 앞쪽 단위 방향 벡터로 바꾼다. 두 입력의 모양은 같거나 서로 확장 가능해야 한다."""
    az, el = np.broadcast_arrays(np.deg2rad(azimuths_deg), np.deg2rad(elevations_deg))
    return np.stack((np.sin(az) * np.cos(el), np.sin(el), np.cos(az) * np.cos(el)), axis=-1)


def validate_inputs(samples, sample_rate, positions, block_size):
    """계산 전에 채널 수·값·마이크 배치를 확인한다."""
    samples = np.asarray(samples)
    positions = np.asarray(positions, dtype=float)
    if np.iscomplexobj(samples):
        raise ValueError("녹음은 복소수가 아닌 실제 소리 샘플이어야 해.")
    samples = np.asarray(samples, dtype=float)
    if samples.ndim != 2 or positions.ndim != 2 or positions.shape[1] != 3:
        raise ValueError("녹음은 (샘플 수, 채널 수), 좌표는 (마이크 수, 3) 모양이어야 해.")
    if samples.shape[1] != len(positions):
        raise ValueError("WAV 채널 수와 마이크 좌표 개수가 달라.")
    if not 3 <= len(positions) <= 64:
        raise ValueError("3~64개 마이크가 필요해. 재생용 2채널 WAV는 마이크 녹음이 아니야.")
    if not np.all(np.isfinite(samples)) or not np.all(np.isfinite(positions)):
        raise ValueError("녹음이나 좌표에 NaN·무한대 같은 잘못된 숫자가 있어.")
    if not isinstance(sample_rate, (int, np.integer)) or sample_rate < 8000:
        raise ValueError("샘플링 주파수는 8000Hz 이상의 정수여야 해.")
    if not isinstance(block_size, (int, np.integer)) or block_size < 64 or block_size % 2:
        raise ValueError("FFT 구간 길이는 64 이상의 짝수 정수여야 해.")
    if len(samples) < block_size:
        raise ValueError(f"녹음이 너무 짧아. 최소 {block_size}개 샘플이 필요해.")
    if len(np.unique(positions, axis=0)) != len(positions):
        raise ValueError("마이크 좌표가 중복돼 있어.")
    if not np.allclose(positions[:, 2], positions[0, 2], atol=1e-9, rtol=0):
        raise ValueError("이번 버전은 모든 마이크가 같은 z 평면에 있는 배열을 지원해.")
    centered = positions[:, :2] - positions[:, :2].mean(axis=0)
    if np.linalg.matrix_rank(centered) < 2:
        raise ValueError("마이크가 한 직선에만 놓여 있어 두 방향을 계산할 수 없어.")
    if np.any(np.std(samples, axis=0) < 1e-10):
        raise ValueError("무음이거나 값이 고정된 채널이 있어. 녹음 시작 시점과 채널을 확인해 줘.")
    return samples, positions


def cross_spectral_matrix(samples, sample_rate, block_size, fmin, fmax):
    """여러 짧은 구간의 주파수별 마이크 관계를 평균한다 (Welch, 50% 겹침)."""
    if not np.isfinite(fmin) or not np.isfinite(fmax) or not 0 < fmin < fmax <= sample_rate / 2:
        raise ValueError("주파수 범위는 0 < fmin < fmax ≤ 샘플링 주파수/2여야 해.")
    all_frequencies = np.fft.rfftfreq(block_size, d=1 / sample_rate)
    selected = (all_frequencies >= fmin) & (all_frequencies <= fmax)
    if not np.any(selected):
        raise ValueError("선택한 대역에 FFT 주파수가 없어. 대역을 넓히거나 FFT 길이를 늘려 줘.")
    frequencies = all_frequencies[selected]
    microphone_count = samples.shape[1]
    csm = np.zeros((len(frequencies), microphone_count, microphone_count), dtype=complex)
    window = np.hanning(block_size)
    frame_count = 0
    for start in range(0, len(samples) - block_size + 1, block_size // 2):
        block = samples[start:start + block_size]
        block = block - block.mean(axis=0)
        spectrum = np.fft.rfft(block * window[:, None], axis=0)[selected]
        # CSM[f, m, n] = X_m * conjugate(X_n)의 평균. 마이크 간 위상도 보관한다.
        csm += spectrum[:, :, None] * spectrum[:, None, :].conj()
        frame_count += 1

    # 양의 주파수만 보관하므로 DC와 Nyquist 이외에는 음의 주파수 몫까지 2배로 반영한다.
    factors = np.full(len(frequencies), 2.0)
    factors[frequencies == 0] = 1
    if block_size % 2 == 0:
        factors[frequencies == sample_rate / 2] = 1
    csm *= (factors / (frame_count * sample_rate * np.sum(window ** 2)))[:, None, None]
    band_power = np.trace(csm, axis1=1, axis2=2).real.sum() * sample_rate / block_size / microphone_count
    total_power = np.mean(np.var(samples, axis=0))
    if band_power < max(1e-20, total_power * 1e-10):
        raise ValueError("선택한 주파수 대역에 소리가 거의 없어. fmin·fmax를 확인해 줘.")
    return csm, frequencies, frame_count


def scan_power(csm, frequencies_hz, positions, vectors, sound_speed, frequency_step):
    """각 방향에서 시간차를 보정하고 더한 신호의 평균 제곱값을 구한다."""
    positions = positions - positions.mean(axis=0)
    # 각 방향과 각 마이크 위치의 내적. 3개 좌표를 곱해 더한다.
    projected_times = np.einsum("gd,md->gm", vectors, positions) / sound_speed
    power = np.zeros(len(vectors))
    for frequency, matrix in zip(frequencies_hz, csm):
        # 이 방향에서 온 소리는 X_m ≈ S * exp(+j*2πf*r_m·u/c).
        # 반대 위상의 가중치를 곱하면 마이크 간 시간차가 맞춰진다.
        weights = np.exp(-2j * np.pi * frequency * projected_times) / len(positions)
        power += np.einsum("gm,mn,gn->g", weights, matrix, weights.conj(), optimize=True).real
    return np.maximum(power * frequency_step, 0)


def beamform(samples, sample_rate, positions, *, fmin=500.0, fmax=4000.0,
             temperature_c=20.0, azimuths_deg=None, elevations_deg=None, block_size=1024):
    """지연-합 빔포밍의 진입 함수. 정답 각도나 모터 위치는 입력받지 않는다."""
    samples, positions = validate_inputs(samples, sample_rate, positions, block_size)
    speed = sound_speed_from_temperature(temperature_c)
    azimuths = np.asarray(np.arange(-90, 91, 2) if azimuths_deg is None else azimuths_deg, dtype=float)
    elevations = np.asarray(np.arange(-40, 41, 2) if elevations_deg is None else elevations_deg, dtype=float)
    for values, bound, label in ((azimuths, 90, "가로"), (elevations, 90, "세로")):
        if (values.ndim != 1 or len(values) == 0 or not np.all(np.isfinite(values))
                or np.any(np.diff(values) <= 0) or np.any(np.abs(values) > bound)):
            raise ValueError(f"{label} 각도는 ±{bound}° 안에서 중복 없이 증가하는 숫자 목록이어야 해.")
    # 세로 ±90°에서는 모든 가로 각도가 같은 방향이 되어 가로 좌표가 정해지지 않는다.
    if np.any(np.abs(elevations) >= 90):
        raise ValueError("세로 각도는 -90°보다 크고 +90°보다 작아야 해.")
    csm, frequencies, frame_count = cross_spectral_matrix(samples, sample_rate, block_size, fmin, fmax)
    az_grid, el_grid = np.meshgrid(azimuths, elevations)
    vectors = direction_vectors(az_grid.ravel(), el_grid.ravel())
    power = scan_power(csm, frequencies, positions, vectors, speed, sample_rate / block_size)
    if not np.all(np.isfinite(power)) or power.max() <= 0:
        raise ValueError("유효한 소리 세기를 계산하지 못했어.")
    return BeamformingResult(azimuths, elevations, power.reshape(el_grid.shape), frequencies,
                             frame_count, sample_rate, block_size, speed)
