"""4단계: 16채널 녹음 + 지연-합 빔포밍 (책상 위, 회전판 없이).

    python step4_beamform.py --sim 30                    # 장치 없이 프로그램 점검 (30° 가짜 소리)
    python step4_beamform.py --true 0                    # 스피커 A를 정면에 두고 녹음·계산
    python step4_beamform.py --true 30 --sound exp1_tone_2k --band 1800 2200
    python step4_beamform.py --wav 기록/bf_....wav       # 저장한 녹음을 다시 계산
    python step4_beamform.py --true -30 30 --sound exp2_band_4k --speaker AB --band 3500 4500   # A·B 동시

UMA-16은 세워 두고(마이크 면이 스피커 쪽, USB 단자 아래), 스피커 A는 배열 중심과 같은 높이로 1m쯤 떨어뜨린다.
--true는 줄자·각도기로 잰 실제 각도이다. 배열 뒤에서 스피커를 볼 때 오른쪽이 +이다.
A·B 동시(--speaker AB)일 때는 --true에 두 각도를 주고, 최대보다 6 dB 안의 봉우리를 모두 보여 준다.
녹음은 기록/bf_날짜.wav, 결과는 기록/bf_log.csv 에 한 줄씩 쌓인다.
녹음·재생은 팀원의 ../sh/sound_io.py를 그대로 불러 쓴다.
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

import beamform as bf

HERE = Path(__file__).resolve().parent
LOG = HERE / "기록" / "bf_log.csv"
FS = 48000


def show(angles, p, true=()):
    """5° 간격 막대그래프 (dB, −20 dB까지)."""
    width = 40
    for a in range(-90, 91, 5):
        v = 10 * np.log10(max(p[np.argmin(np.abs(angles - a))], 1e-10))
        n = int(np.clip((v + 20) / 20, 0, 1) * width)
        mark = "  ← 실제" if any(abs(a - t) < 2.5 for t in true) else ""
        print(f"  {a:+4d}° {v:6.1f} dB |{'#' * n}{' ' * (width - n)}|{mark}")


def record(args):
    sys.path.insert(0, str(HERE.parent / "sh"))
    from sound_io import SoundIO

    sio = SoundIO()
    print(f"재생: {args.sound} → 스피커 {args.speaker}, 볼륨 {args.volume}")
    rec, info = sio.play_and_record(args.sound, args.speaker, volume=args.volume)
    print(f"녹음 {info['rec_s']}초, 최대 크기 {info['peak']}" + (f", 경고 {info['warnings']}" if info["warnings"] else ""))
    if info["peak"] >= 0.99:
        print("! 찌그러졌어요. --volume이나 앰프 볼륨을 줄이세요.")
    elif info["peak"] < 0.01:
        print("! 소리가 너무 작아요. 스피커 연결과 볼륨을 확인하세요.")
    label = "".join(f"_{t:+.0f}" for t in args.true) + "deg" if args.true else ""
    path = sio.save(rec, HERE / "기록" / f"bf_{datetime.now():%Y%m%d_%H%M%S}{label}.wav")
    return rec.astype(float) / 32768, path, info["peak"]


def main():
    ap = argparse.ArgumentParser(description="16채널 녹음 + 지연-합 빔포밍")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--sim", type=float, nargs="+", metavar="각도", help="가짜 소리로 점검 (여러 개면 동시에)")
    src.add_argument("--wav", help="저장한 16채널 wav를 계산")
    ap.add_argument("--true", type=float, nargs="+", default=[], help="실제 스피커 각도 (°), A·B 동시면 두 개")
    ap.add_argument("--sound", default="exp1_white")
    ap.add_argument("--speaker", default="A")
    ap.add_argument("--volume", type=float, default=0.3)
    ap.add_argument("--band", type=float, nargs=2, default=(300, 4000), metavar=("낮은Hz", "높은Hz"))
    ap.add_argument("--temp", type=float, default=20.0, help="기온 (°C), 음속 보정")
    args = ap.parse_args()

    peak, path = None, ""
    if args.sim is not None:
        rec = bf.simulate(args.sim, FS, temp_c=args.temp)
        args.true = args.true or args.sim
        print("가짜 소리: " + ", ".join(f"{a:+.1f}°" for a in args.sim) + " 백색잡음")
    elif args.wav:
        import soundfile as sf

        rec, fs = sf.read(args.wav)
        if fs != FS or rec.ndim != 2 or rec.shape[1] != 16:
            print(f"48 kHz 16채널 wav가 아니에요 ({fs} Hz, 모양 {rec.shape}).")
            return
        path = args.wav
    else:
        rec, path, peak = record(args)

    angles, p = bf.scan(rec, FS, band=tuple(args.band), temp_c=args.temp)
    est = float(angles[np.argmax(p)])
    bw = bf.beam_width(angles, p)
    peaks = bf.find_peaks(angles, p)
    print(f"\n대역 {args.band[0]:.0f}~{args.band[1]:.0f} Hz, 음속 {bf.sound_speed(args.temp):.1f} m/s")
    show(angles, p, args.true)
    if len(args.true) <= 1:
        t = args.true[0] if args.true else None
        print(f"\n추정 각도 {est:+.0f}°" + (f", 실제 {t:+.1f}°, 오차 {est - t:+.1f}°" if t is not None else "")
              + (f", 빔 폭(−3 dB) {bw:.0f}°" if bw else ""))
    else:
        print(f"\n실제 " + ", ".join(f"{t:+.0f}°" for t in args.true)
              + " → 봉우리(최대 −6 dB 안) " + ", ".join(f"{a:+.0f}°" for a in peaks))
        if len(peaks) >= 2:
            lo, hi = sorted(peaks[:2])
            dip = 10 * np.log10(p[(angles > lo) & (angles < hi)].min())
            print(f"두 봉우리 사이 골 {dip:.1f} dB → " + ("분리됨" if dip <= -3 else "골이 얕음(−3 dB보다 위)"))
        else:
            print("봉우리가 하나뿐 → 두 소리가 합쳐져 보임(분리 안 됨)")

    if args.sim is None:
        LOG.parent.mkdir(exist_ok=True)
        new = not LOG.exists()
        with open(LOG, "a", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            if new:
                w.writerow(["time", "true_deg", "est_deg", "err_deg", "beam_width_deg", "sound", "band_lo", "band_hi",
                            "temp_c", "peak", "wav", "peaks_deg"])
            true = " ".join(f"{t:g}" for t in args.true)
            err = round(est - args.true[0], 1) if len(args.true) == 1 else ""
            w.writerow([datetime.now().isoformat(timespec="seconds"), true, est, err, bw,
                        args.sound if not args.wav else "", args.band[0], args.band[1], args.temp, peak,
                        Path(path).name if path else "", " ".join(f"{a:g}" for a in peaks)])
        print(f"기록: {LOG}")


if __name__ == "__main__":
    main()
