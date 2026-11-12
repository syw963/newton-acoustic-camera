"""지연-합(delay-and-sum) 빔포밍.

UMA-16을 세워 두고(마이크 면이 스피커 쪽, USB 단자 아래) 가로 방향 각도 θ를 찾는다.

    from beamform import scan
    angles, p = scan(rec, 48000)          # rec: (표본 수, 16), p: 각도별 세기 (최대 1)
    print(angles[p.argmax()])

각도 약속(임시, 팀 논의 D3에서 확정): 0°는 배열 정면, θ > 0은 배열 뒤(카메라 쪽)에서
스피커를 볼 때 오른쪽이다. 마이크 좌표의 x는 스피커 쪽에서 볼 때 오른쪽이 +이므로
θ > 0인 소리는 x < 0인 마이크에 먼저 닿는다.
"""

import numpy as np

# 채널 순서(0번 = ch1), 배열 중심 기준 mm. 스피커 쪽에서 볼 때 x 오른쪽 +, y 위쪽 +.
# 설계_및_결정사항.md "UMA-16 채널 위치표" (2026-11-11)
MIC_XY_MM = [(-21, -63), (-63, -63), (-21, -21), (-63, -21), (-21, +21), (-63, +21), (-21, +63), (-63, +63),
             (+63, +63), (+21, +63), (+63, +21), (+21, +21), (+63, -21), (+21, -21), (+63, -63), (+21, -63)]
MIC_XY = np.array(MIC_XY_MM, dtype=float) / 1000  # m
MIC_X = MIC_XY[:, 0]


def sound_speed(temp_c):
    return 331.3 + 0.606 * temp_c


def arrival_delays(angles_deg, temp_c=20.0):
    """평면파가 배열 중심보다 각 마이크에 늦게 닿는 시간 (s). 모양 (각도 수, 16)."""
    s = np.sin(np.radians(np.atleast_1d(angles_deg)))
    return s[:, None] * MIC_X[None, :] / sound_speed(temp_c)


def arrival_delays_2d(az_deg, el_deg, temp_c=20.0):
    """가로 az(뒤에서 볼 때 오른쪽 +)·세로 el(위쪽 +) 방향마다 늦게 닿는 시간 (s). 모양 (방향 수, 16).
    위에서 온 소리는 y > 0인 마이크에 먼저 닿는다. el = 0이면 arrival_delays와 같다."""
    az, el = np.radians(np.ravel(az_deg)), np.radians(np.ravel(el_deg))
    return ((np.sin(az) * np.cos(el))[:, None] * MIC_XY[None, :, 0]
            - np.sin(el)[:, None] * MIC_XY[None, :, 1]) / sound_speed(temp_c)


def stft(x, nfft=1024):
    """(표본 수, 채널) → (프레임, 주파수, 채널). 한 프레임 nfft, 절반씩 겹침, 해닝 창."""
    hop = nfft // 2
    win = np.hanning(nfft)[:, None]
    n = (len(x) - nfft) // hop + 1
    frames = np.stack([x[i * hop:i * hop + nfft] * win for i in range(n)])
    return np.fft.rfft(frames, axis=1)


def scan(rec, fs, angles=None, band=(300, 4000), temp_c=20.0, nfft=1024):
    """각도마다 16채널을 지연을 맞춰 더한 세기. (각도 배열, 세기 배열(최대 1))."""
    if angles is None:
        angles = np.arange(-90, 90.5, 1.0)
    x = np.asarray(rec, dtype=float)
    x = x - x.mean(axis=0)
    X = stft(x, nfft)
    f = np.fft.rfftfreq(nfft, 1 / fs)
    sel = (f >= band[0]) & (f <= band[1])
    X, f = X[:, sel, :], f[sel]
    tau = arrival_delays(angles, temp_c)                               # (A, 16)
    steer = np.exp(2j * np.pi * f[None, :, None] * tau[:, None, :])    # (A, F, 16): 늦게 닿은 만큼 앞당김
    p = np.zeros(len(angles))
    for i in range(len(angles)):  # 각도마다 따로 계산해 메모리를 아낌
        p[i] = np.sum(np.abs(np.einsum("tfm,fm->tf", X, steer[i])) ** 2)
    return angles, p / p.max()


def beam_width(angles, p):
    """봉우리에서 −3 dB(세기 절반)까지의 폭 (°). 범위 끝에 닿으면 None."""
    k = int(np.argmax(p))
    lo = k
    while lo > 0 and p[lo] >= 0.5:
        lo -= 1
    hi = k
    while hi < len(p) - 1 and p[hi] >= 0.5:
        hi += 1
    if p[lo] >= 0.5 or p[hi] >= 0.5:
        return None
    return float(angles[hi] - angles[lo])


def find_peaks(angles, p, floor_db=-6.0):
    """봉우리(양옆보다 큰 점) 중 최대보다 floor_db 이상 큰 것의 각도, 큰 순서."""
    k = [i for i in range(1, len(p) - 1) if p[i] >= p[i - 1] and p[i] > p[i + 1]]
    k += [i for i in (0, len(p) - 1) if p[i] == p.max()]
    k = [i for i in k if 10 * np.log10(p[i]) >= floor_db]
    return [float(angles[i]) for i in sorted(k, key=lambda i: -p[i])]


def simulate(angle_deg, fs=48000, seconds=2.0, temp_c=20.0, snr_db=20.0, seed=0):
    """θ 방향 백색잡음이 16채널에 닿은 가짜 녹음 (표본 수, 16). 프로그램 점검용.
    angle_deg에 여러 각도를 주면 서로 다른 잡음 여러 개를 더한다."""
    rng = np.random.default_rng(seed)
    n = int(fs * seconds)
    f = np.fft.rfftfreq(n, 1 / fs)
    x = 0
    for tau in arrival_delays(angle_deg, temp_c):
        S = np.fft.rfft(rng.standard_normal(n))
        x = x + np.fft.irfft(S[:, None] * np.exp(-2j * np.pi * f[:, None] * tau[None, :]), n, axis=0)
    x += rng.standard_normal(x.shape) * x.std() * 10 ** (-snr_db / 20)
    return x
