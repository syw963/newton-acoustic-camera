"""녹음 공급원: 가짜 녹음(시뮬레이터)과 회전판으로 모은 실제 녹음.

    for rec, angle, temp, group in iter_sim(100, seed=0): ...
    for rec, angle, temp, group in iter_session("수집/20261120_과학실"): ...

rec은 (표본 수, 16) float, angle은 정답 각도(°, 배열 뒤에서 볼 때 오른쪽 +), group은 세션 이름이다.
group은 학습/시험을 나눌 때 쓴다. 같은 세션 녹음을 무작위로 섞어 나누지 않는다(data leakage).
"""

import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "파이썬"))
import beamform as bf  # noqa: E402  마이크 좌표, 도착 지연

FS = 48000


def _delay(S, f, tau):
    """스펙트럼 S (주파수,)를 마이크마다 tau (16,)만큼 늦춘 스펙트럼 (주파수, 16)."""
    return S[:, None] * np.exp(-2j * np.pi * f[:, None] * tau[None, :])


def sim_one(angle, rng, seconds=0.5, temp_c=20.0):
    """θ 방향 음원 + 반사 1~3개 + 마이크 감도 차이 + 잡음. 실제 방보다 단순하지만 프로그램 점검과 사전 학습용."""
    n = int(FS * seconds)
    f = np.fft.rfftfreq(n, 1 / FS)
    # 음원: 백색잡음 또는 대역 잡음 (스피커 소리 종류를 흉내)
    S = np.fft.rfft(rng.standard_normal(n))
    if rng.random() < 0.5:
        fc = rng.uniform(1000, 6000)
        S *= np.exp(-0.5 * (np.log2(np.maximum(f, 1) / fc) / 0.5) ** 2)
    S *= (f > 200) & (f < 10000)
    X = _delay(S, f, bf.arrival_delays_2d(angle, rng.uniform(-5, 5), temp_c)[0])
    # 반사: 다른 방향에서 1~10 ms 늦게, 0.1~0.5배로 (벽·책상)
    for _ in range(rng.integers(1, 4)):
        tau = bf.arrival_delays_2d(rng.uniform(-90, 90), rng.uniform(-40, 40), temp_c)[0]
        X += rng.uniform(0.1, 0.5) * _delay(S * np.exp(-2j * np.pi * f * rng.uniform(1e-3, 10e-3)), f, tau)
    x = np.fft.irfft(X, n, axis=0)
    x *= 10 ** (rng.normal(0, 1, 16) / 20)                  # 마이크 감도 ±1 dB
    snr = rng.uniform(0, 30)
    x += rng.standard_normal(x.shape) * x.std() * 10 ** (-snr / 20)
    return x


def iter_sim(n, seed=0, angle_range=60.0, group="sim"):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        angle = rng.uniform(-angle_range, angle_range)
        temp = rng.uniform(15, 28)
        yield sim_one(angle, rng, temp_c=temp), angle, temp, group


def iter_session(folder):
    """collect.py가 만든 폴더(labels.csv + wav)를 읽는다."""
    import soundfile as sf

    folder = Path(folder)
    with open(folder / "labels.csv", encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            rec, fs = sf.read(folder / row["wav"])
            if fs != FS or rec.ndim != 2 or rec.shape[1] != 16:
                print(f"건너뜀: {row['wav']} ({fs} Hz, 모양 {rec.shape})")
                continue
            yield rec, float(row["angle_deg"]), float(row["temp_c"]), folder.name
