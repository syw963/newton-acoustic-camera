"""GCC-PHAT 특징과 SRP-PHAT.

16개 마이크에서 두 개씩 고른 120쌍마다 "두 마이크에 소리가 닿은 시간차"가 어디쯤인지 보여 주는
곡선(GCC-PHAT)을 구한다. 딥러닝 입력은 이 120개 곡선을 쌓은 (120, 2L+1) 배열이다.

PHAT: 크기를 1로 나눠 위상(시간차)만 남긴다. 소리 종류(스펙트럼)가 바뀌어도 모양이 덜 변한다.
"""

from itertools import combinations

import numpy as np

import data
from data import bf

PAIRS = np.array(list(combinations(range(16), 2)))   # (120, 2)
MAX_LAG = 32       # ±32 표본 = ±0.67 ms. 가장 먼 두 마이크(대각선 178 mm)도 0.52 ms 안이다
NFFT = 1024
BAND = (300, 8000)


def cross_spectra(rec, nfft=NFFT, band=BAND):
    """쌍마다 PHAT 정규화한 평균 교차 스펙트럼 (120, 주파수). 띠 밖은 0."""
    x = np.asarray(rec, float)
    X = bf.stft(x - x.mean(axis=0), nfft)                                  # (T, F, 16)
    G = np.einsum("tfp,tfp->pf", X[:, :, PAIRS[:, 0]], X[:, :, PAIRS[:, 1]].conj()) / len(X)
    G /= np.abs(G) + 1e-12
    f = np.fft.rfftfreq(nfft, 1 / data.FS)
    G[:, (f < band[0]) | (f > band[1])] = 0
    return G


def gcc_phat(rec, max_lag=MAX_LAG, up=1, nfft=NFFT, band=BAND):
    """(120, 2·max_lag·up + 1). 가운데 칸이 시간차 0, 오른쪽으로 갈수록 첫 마이크가 늦게 받음.
    up은 시간 칸을 몇 배로 잘게 나눌지(0을 채워 늘린 역FFT)."""
    G = cross_spectra(rec, nfft, band)
    n = nfft * up
    r = np.fft.irfft(G, n, axis=1) * up
    L = max_lag * up
    return np.concatenate([r[:, -L:], r[:, :L + 1]], axis=1).astype(np.float32)


def srp_phat(rec, angles=None, temp_c=20.0, up=8):
    """SRP-PHAT: 각도마다 120쌍의 GCC-PHAT 값을 그 각도의 시간차 자리에서 읽어 더한다. (각도, 세기)."""
    if angles is None:
        angles = np.arange(-90, 90.25, 0.5)
    r = gcc_phat(rec, up=up)
    tau = bf.arrival_delays(angles, temp_c)                                 # (A, 16)
    lag = (tau[:, PAIRS[:, 0]] - tau[:, PAIRS[:, 1]]) * data.FS * up + MAX_LAG * up
    i = np.arange(len(PAIRS))
    k0 = np.clip(np.floor(lag).astype(int), 0, r.shape[1] - 2)
    w = lag - k0
    p = ((1 - w) * r[i, k0] + w * r[i, k0 + 1]).sum(axis=1)
    return angles, p
