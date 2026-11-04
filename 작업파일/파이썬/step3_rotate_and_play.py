"""3단계: 돌리고 → 기다리고 → 소리 내기를 반복한다.

나중의 자동 데이터 수집과 같은 흐름이다. UMA-16이 도착하면 '소리 내기' 자리에
'소리 내면서 16채널 녹음'이 들어간다. 지금은 녹음 없이 기록(csv)만 남긴다.

    python step3_rotate_and_play.py --port sim --no-sound        # 아무 장치 없이
    python step3_rotate_and_play.py --port sim                   # 소리만 진짜로
    python step3_rotate_and_play.py --angles -60 -30 0 30 60     # 진짜 회전판
    python step3_rotate_and_play.py --bench --angles -30 0 30    # 조립 전, 리밋 스위치 없이
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import audio
from turntable import Turntable, TurntableError

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description="회전 + 재생 반복")
    ap.add_argument("--port", default=None, help="포트 이름 (비우면 자동, sim은 시뮬레이터)")
    ap.add_argument("--angles", type=float, nargs="+", default=[-60, -30, 0, 30, 60], help="갈 각도들")
    ap.add_argument("--freq", type=float, default=1000, help="순음 주파수 Hz")
    ap.add_argument("--seconds", type=float, default=1.0, help="소리 길이")
    ap.add_argument("--settle", type=float, default=0.5, help="도착 후 흔들림이 멈출 때까지 기다리는 시간(초)")
    ap.add_argument("--volume", type=float, default=0.3)
    ap.add_argument("--no-sound", action="store_true", help="소리 없이 회전만")
    ap.add_argument("--bench", action="store_true", help="리밋 스위치 없이 지금 위치를 원점으로 (조립 전)")
    args = ap.parse_args()

    sound = not args.no_sound
    if sound and not audio.available():
        print(audio.why_unavailable(), "\n→ 소리 없이 진행해요 (--no-sound)")
        sound = False

    out_dir = HERE / "기록"
    out_dir.mkdir(exist_ok=True)
    log_path = out_dir / f"step3_{datetime.now():%Y%m%d_%H%M%S}.csv"

    try:
        with Turntable(args.port, verbose=False) as t, open(log_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["순서", "목표_각도", "보고된_각도", "이동_초", "소리", "시각"])
            t.enable(True)
            if args.bench:
                print("벤치 원점: 지금 위치를 0°로 정해요")
                t.bench_origin()
            else:
                print("원점 찾는 중...")
                t.home()
            for i, a in enumerate(args.angles, 1):
                t0 = time.time()
                t.goto(a)
                move_s = time.time() - t0
                time.sleep(args.settle)
                reported = t.status().get("angle_deg")
                what = "없음"
                if sound:
                    audio.play(audio.tone(args.freq, args.seconds), side="A", volume=args.volume)
                    what = f"{args.freq:.0f}Hz {args.seconds}s A"
                w.writerow([i, a, reported, f"{move_s:.2f}", what, datetime.now().isoformat(timespec="seconds")])
                print(f"{i:2d}/{len(args.angles)}  목표 {a:+6.1f}°  보고 {reported:+8.3f}°  이동 {move_s:.1f}초  소리 {what}")
            t.goto(0)
            t.enable(False)
    except TurntableError as e:
        print(f"오류: {e}")
        return
    print(f"기록 저장: {log_path}")


if __name__ == "__main__":
    main()
