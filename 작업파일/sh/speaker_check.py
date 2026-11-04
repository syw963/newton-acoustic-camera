"""스피커 확인: 소리를 내면서 노트북 마이크로 녹음해 숫자로 판정한다. 녹음은 저장하지 않는다.

  python speaker_check.py          채널 확인 소리(A 1 kHz → B 2 kHz): 소리가 나는지, 순서, 찌그러짐, 웅 잡음
  python speaker_check.py --ab     1 kHz를 A만, B만 차례로 → 크기 비교
                                   노트북(마이크)을 스피커 A 바로 앞에 두면 A 쪽이 커야 한다

옵션: --mic (기본 default = 노트북 마이크), --volume (기본 0.3)

주의 (11/4 확인): 노트북 마이크(인텔 스마트 사운드 마이크 배열 등)는 잡음 제거가 켜져 있으면
계속되는 순음을 지워 버려 시간표가 L·H 조각으로 흩어진다. 조용한 구간이 −120 dB(완전한 0)로 나오면 이 경우다.
Windows 설정 → 소리 → 입력 → 마이크 → "오디오 향상"을 끄거나, UMA-16(--mic uma16)으로 쓴다.
"""
import argparse
import sys

import numpy as np

import sound_io as s

FS = s.FS


def band_db(x, f, width=20):
    """x에서 주파수 f 근처(±width Hz)의 가장 큰 성분 크기 (dB, 기준 1)."""
    w = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * w)) / (np.sum(w) / 2)
    freqs = np.fft.rfftfreq(len(x), 1 / FS)
    sel = (freqs >= f - width) & (freqs <= f + width)
    return 20 * np.log10(spec[sel].max() + 1e-12)


def thd_percent(x, f0, n=5):
    """기본음 f0에 대한 2~n배음의 크기 합 비율 (%). 클수록 찌그러짐."""
    fund = 10 ** (band_db(x, f0) / 20)
    harm = [10 ** (band_db(x, f0 * k) / 20) for k in range(2, n + 1) if f0 * k < FS / 2 - 1000]
    return 100 * np.sqrt(np.sum(np.square(harm))) / fund


def hum_db(x):
    """60·120 Hz 성분이 주변(40~300 Hz) 중간값보다 몇 dB 큰가. 15 dB 넘으면 웅 잡음 의심."""
    w = np.hanning(len(x))
    spec = 20 * np.log10(np.abs(np.fft.rfft(x * w)) + 1e-12)
    freqs = np.fft.rfftfreq(len(x), 1 / FS)
    ref = np.median(spec[(freqs >= 40) & (freqs <= 300)])
    return max(band_db(x, 60, 3), band_db(x, 120, 3)) - (ref - 20 * np.log10(np.sum(w) / 2))


def seg(x, t0, t1):
    return x[max(0, int(t0 * FS)):int(t1 * FS)]


FRAME = 0.1   # 시간표 한 칸 (s)


def timeline(x):
    """0.1초마다 1 kHz, 2 kHz 크기(dB)를 잰다."""
    n = int(FRAME * FS)
    k = len(x) // n
    l1 = np.array([band_db(x[i * n:(i + 1) * n], 1000, 30) for i in range(k)])
    l2 = np.array([band_db(x[i * n:(i + 1) * n], 2000, 30) for i in range(k)])
    return l1, l2


def runs(mask):
    """True가 이어진 구간들 [(시작 칸, 끝 칸)]"""
    out, start = [], None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append((start, i))
            start = None
    return out


def check_channel(sio, volume):
    rec, info = sio.play_and_record("00_채널확인", "AB", volume=volume)
    x = rec.astype(np.float32).mean(axis=1) / 32768          # 마이크 채널 평균
    print(f"녹음 {info['rec_s']} s, 최대 크기 {info['peak']:.3f}")
    l1, l2 = timeline(x)
    floor = min(np.median(np.sort(l1)[:len(l1) // 4]), np.median(np.sort(l2)[:len(l2) // 4]))
    low = (l1 > floor + 15) & (l1 > l2 + 10)       # 1 kHz가 뚜렷한 칸
    high = (l2 > floor + 15) & (l2 > l1 + 10)      # 2 kHz가 뚜렷한 칸
    line = "".join("L" if a else "H" if b else "." for a, b in zip(low, high))
    print(f"시간표 (한 칸 0.1 s, L = 1 kHz 낮은 소리, H = 2 kHz 높은 소리, . = 그 밖)")
    print("  " + line)
    print(f"  조용할 때 크기 약 {floor:.0f} dB, 1 kHz 최대 {l1.max():.0f} dB, 2 kHz 최대 {l2.max():.0f} dB")

    lr, hr = runs(low), runs(high)
    lmain = max(lr, key=lambda r: r[1] - r[0], default=None)
    hmain = max(hr, key=lambda r: r[1] - r[0], default=None)
    print()
    print("판정 (기대: 낮은 소리 약 2초 → 0.5초 쉼 → 높은 소리 약 2초)")
    if lmain is None or hmain is None:
        print(f"  낮은 소리 {'있음' if lmain else '없음'}, 높은 소리 {'있음' if hmain else '없음'}")
        print("  → 소리가 충분히 녹음되지 않았다. 앰프 볼륨을 조금 올리거나 노트북을 스피커 가까이 둔다.")
        return 1
    ld, hd = (lmain[1] - lmain[0]) * FRAME, (hmain[1] - hmain[0]) * FRAME
    order_ok = lmain[0] < hmain[0]
    print(f"  낮은 소리 {lmain[0] * FRAME:.1f}~{lmain[1] * FRAME:.1f} s ({ld:.1f} s), "
          f"높은 소리 {hmain[0] * FRAME:.1f}~{hmain[1] * FRAME:.1f} s ({hd:.1f} s)")
    print(f"  순서 (낮은 → 높은) : {'맞음' if order_ok else '반대'}")
    print(f"  길이 (각 약 2초)   : {'맞음' if ld >= 1.5 and hd >= 1.5 else '짧음 (소리가 끊기거나 작다)'}")

    n = int(FRAME * FS)
    first = x[(lmain[0] + 2) * n:(lmain[1] - 2) * n]
    quiet = x[:max(lmain[0] - 1, 0) * n]
    thd = thd_percent(first, 1000) if len(first) > n else float("nan")
    hum = hum_db(quiet) if len(quiet) > FS // 4 else float("nan")
    print(f"  찌그러짐 (1 kHz 배음 비율 {thd:.1f} %) : "
          f"{'적음' if thd < 5 else '조금 있음 (볼륨을 조금 낮춰 본다)' if thd < 10 else '큼 (앰프 볼륨을 낮춘다)'}")
    print(f"  웅 잡음 (60·120 Hz {hum:+.1f} dB) : {'없음' if not hum > 15 else '있음 (노트북 충전기를 빼고 다시 해 본다)'}")
    if info["peak"] >= 0.99:
        print("  ! 마이크 입력이 꽉 찼다. 노트북을 스피커에서 조금 멀리 둔다.")
    return 0 if order_ok and ld >= 1.5 and hd >= 1.5 else 1


def check_ab(sio, volume):
    levels = {}
    for spk in ("A", "B"):
        print(f"1 kHz → 스피커 {spk} ...", flush=True)
        rec, _ = sio.play_and_record("exp1_tone_1k", spk, volume=volume)
        x = rec.astype(np.float32).mean(axis=1) / 32768
        onset = s.find_onset(x, s.PRE_ROLL)
        if onset is None:
            print(f"  스피커 {spk}: 소리가 녹음되지 않았다.")
            levels[spk] = None
            continue
        t = onset / FS
        levels[spk] = band_db(seg(x, t + 0.3, t + 2.7), 1000)
        print(f"  스피커 {spk}: 1 kHz {levels[spk]:.1f} dB")
    if None in levels.values():
        return 1
    d = levels["A"] - levels["B"]
    print()
    print(f"A가 B보다 {d:+.1f} dB")
    if d > 3:
        print("판정: 노트북 가까운 쪽이 A로 나왔다. (노트북을 스피커 A 앞에 두었다면 맞음)")
    elif d < -3:
        print("판정: 노트북 가까운 쪽이 B로 나왔다. (노트북을 스피커 A 앞에 두었다면 A·B가 바뀐 것)")
    else:
        print("판정: 차이가 작아 구분이 어렵다. 노트북을 한쪽 스피커에 더 가까이 붙이고 다시 한다.")
    return 0


def main():
    p = argparse.ArgumentParser(description="스피커 확인 (녹음은 저장하지 않음)")
    p.add_argument("--ab", action="store_true", help="A만, B만 크기 비교")
    p.add_argument("--mic", default="default")
    p.add_argument("--volume", type=float, default=s.VOLUME)
    args = p.parse_args()
    sio = s.SoundIO(mic=args.mic)
    print(f"마이크: {sio._name(sio.mic)} / 출력: {sio._name(sio.speaker)}")
    return check_ab(sio, args.volume) if args.ab else check_channel(sio, args.volume)


if __name__ == "__main__":
    sys.exit(main())
