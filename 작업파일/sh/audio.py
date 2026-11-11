"""소리 재생 도우미.

노트북 이어폰 단자 → 앰프(PAM8403) → 왼쪽 채널은 스피커 A, 오른쪽 채널은 스피커 B.
그래서 "스피커 A로 소리 내기"는 "왼쪽 채널에만 소리를 넣고 오른쪽은 0"과 같다.

    from audio import tone, play
    play(tone(1000, 1.0), side="A")   # 1 kHz 1초를 스피커 A로
"""

import numpy as np

FS = 48000  # UMA-16 녹음과 같은 표본화 주파수

try:
    import sounddevice as sd
    _SD_ERR = None
except Exception as e:  # 설치 안 됨, 또는 PortAudio 없음
    sd = None
    _SD_ERR = e


def available():
    return sd is not None


def why_unavailable():
    return f"sounddevice를 쓸 수 없어요: {_SD_ERR}. pip install -r requirements.txt 를 확인하세요."


def tone(freq_hz, seconds, fs=FS, fade_s=0.01):
    """순음. 시작과 끝을 10 ms 동안 부드럽게 키우고 줄여 '딱' 소리를 막는다."""
    t = np.arange(int(seconds * fs)) / fs
    x = np.sin(2 * np.pi * freq_hz * t)
    n = int(fade_s * fs)
    if n > 0 and len(x) > 2 * n:
        ramp = np.linspace(0, 1, n)
        x[:n] *= ramp
        x[-n:] *= ramp[::-1]
    return x.astype(np.float32)


def to_stereo(x, side):
    """모노 신호를 A(왼쪽), B(오른쪽), AB(둘 다)로 보낸다. 이미 스테레오면 그대로."""
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 2 and x.shape[1] == 2:
        return x
    if x.ndim == 2:
        x = x[:, 0]
    z = np.zeros_like(x)
    side = side.upper()
    if side == "A":
        return np.column_stack([x, z])
    if side == "B":
        return np.column_stack([z, x])
    return np.column_stack([x, x])


def play(x, side="A", fs=FS, volume=0.3, device=None):
    """소리를 내고 끝날 때까지 기다린다. volume은 0~1 (처음엔 낮게)."""
    if sd is None:
        raise RuntimeError(why_unavailable())
    y = np.clip(to_stereo(x, side) * float(volume), -1.0, 1.0)
    sd.play(y, fs, device=device)
    sd.wait()


def list_devices():
    """[(번호, 이름, 입력 채널, 출력 채널, 기본 출력인지)]"""
    if sd is None:
        return []
    out = []
    try:
        default_out = sd.default.device[1]
    except Exception:
        default_out = None
    for i, d in enumerate(sd.query_devices()):
        out.append((i, d["name"], d["max_input_channels"], d["max_output_channels"], i == default_out))
    return out
