"""실험용 소리 파일 만들기 (스테레오 wav, 48 kHz, 16비트)

왼쪽 채널 = 스피커 A, 오른쪽 채널 = 스피커 B.
사용법: python make_signals.py [저장할 폴더]   (기본: ./signals)

만드는 파일
- 00_채널확인.wav     : 왼쪽(A)만 1 kHz 2초 → 쉼 → 오른쪽(B)만 2 kHz 2초. 배선 확인용
- exp1_*.wav          : 실험 1. 스피커 A만. 순음 1·2·4·6·8 kHz, 백색잡음 (각 3초)
- exp2_*.wav          : 실험 2. A와 B에 서로 다른 난수로 만든 1/3옥타브 대역 잡음 (2·4·6·8 kHz, 각 3초)
                        같은 주파수의 순음 두 개는 위상이 고정되어 간섭하므로 쓰지 않는다.
- exp3_*.wav          : 실험 3. 스피커 A만. 백색잡음, 처프(300 Hz→8 kHz) (각 2초)

모든 파일은 최대 −6 dBFS, 앞뒤 20 ms 페이드. 노트북 소리 향상(공간 음향 등)은 꺼야 한다.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfiltfilt, chirp

FS = 48000
PEAK = 10 ** (-6 / 20)  # −6 dBFS


def fade(x, ms=20):
    n = int(FS * ms / 1000)
    w = np.ones(len(x))
    w[:n] = np.linspace(0, 1, n)
    w[-n:] = np.linspace(1, 0, n)
    return x * w


def norm(x):
    return x / np.max(np.abs(x)) * PEAK


def tone(f, sec):
    t = np.arange(int(FS * sec)) / FS
    return norm(fade(np.sin(2 * np.pi * f * t)))


def white(sec, seed):
    rng = np.random.default_rng(seed)
    return norm(fade(rng.standard_normal(int(FS * sec))))


def third_octave_noise(fc, sec, seed):
    lo, hi = fc / 2 ** (1 / 6), fc * 2 ** (1 / 6)
    sos = butter(6, [lo, hi], btype="bandpass", fs=FS, output="sos")
    rng = np.random.default_rng(seed)
    x = sosfiltfilt(sos, rng.standard_normal(int(FS * sec) + FS))[FS // 2: FS // 2 + int(FS * sec)]
    return norm(fade(x))


def sweep(sec):
    t = np.arange(int(FS * sec)) / FS
    return norm(fade(chirp(t, f0=300, t1=sec, f1=8000, method="logarithmic")))


def save(path, left, right=None):
    if right is None:
        right = np.zeros_like(left)
    st = np.stack([left, right], axis=1)
    wavfile.write(path, FS, (st * 32767).astype(np.int16))


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "signals")
    out.mkdir(parents=True, exist_ok=True)

    gap = np.zeros(FS // 2)
    left = np.concatenate([tone(1000, 2), gap, np.zeros(2 * FS)])
    right = np.concatenate([np.zeros(2 * FS), gap, tone(2000, 2)])
    save(out / "00_채널확인.wav", left, right)

    for f in (1000, 2000, 4000, 6000, 8000):
        save(out / f"exp1_tone_{f // 1000}k.wav", tone(f, 3))
    save(out / "exp1_white.wav", white(3, seed=1))

    for i, f in enumerate((2000, 4000, 6000, 8000)):
        a = third_octave_noise(f, 3, seed=100 + 2 * i)
        b = third_octave_noise(f, 3, seed=101 + 2 * i)  # 다른 난수 → 서로 독립인 음원
        save(out / f"exp2_band_{f // 1000}k.wav", a, b)

    save(out / "exp3_white.wav", white(2, seed=2))
    save(out / "exp3_chirp.wav", sweep(2))
    print(f"{len(list(out.glob('*.wav')))}개 파일 → {out.resolve()}")


if __name__ == "__main__":
    main()
