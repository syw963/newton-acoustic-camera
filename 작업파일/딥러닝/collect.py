"""실험 3 자동 수집: 회전판을 무작위 각도로 돌리고 소리를 내서 16채널을 녹음한다.

    python collect.py --n 300 --place 과학실 --distance 1.0 --temp 22
    python collect.py --n 20 --place 연습 --sim          # 회전판·UMA-16 없이 흐름만 점검

시작 전: 스피커 A를 배열 정면 1 m에 두고, 회전판의 연필 0° 표시를 맞춘다.
프로그램이 그 위치를 원점(o 명령)으로 삼는다. 단순판에는 리밋 스위치가 없으므로
50회마다 0°로 돌아가 빔포밍으로 정면을 확인한다. 3°보다 어긋나면 멈춘다(스텝을 잃었을 가능성).

결과: 수집/날짜_장소/0001.wav … 와 labels.csv. 같은 폴더로 다시 실행하면 이어서 모은다.
각도: 회전판이 +φ 돌면 정면 스피커가 배열 기준 +φ에 보인다(배열 뒤에서 볼 때 오른쪽 +).
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import data
from data import bf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "sh"))
CHECK_EVERY = 50
CHECK_TOL = 3.0
FIELDS = ["wav", "angle_deg", "time", "temp_c", "place", "distance_m", "sound", "peak"]


class FakeAudio:
    """--sim: 회전판 각도를 정답으로 가짜 녹음을 만든다."""

    def __init__(self, table):
        self.table, self.rng = table, np.random.default_rng()

    def play_and_record(self, sound, speaker, volume):
        rec = data.sim_one(self.table.status()["angle_deg"], self.rng, seconds=1.0)
        rec = np.int16(np.clip(rec / np.abs(rec).max() * 0.5, -1, 1) * 32767)
        return rec, {"peak": 0.5}

    @staticmethod
    def save(rec, path):
        import soundfile as sf
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), rec, data.FS, subtype="PCM_16")


def check_zero(table, sio, args):
    table.goto(0)
    time.sleep(0.5)
    rec, _ = sio.play_and_record(args.sound, args.speaker, volume=args.volume)
    a, p = bf.scan(rec.astype(float) / 32768, data.FS, band=(300, 4000), temp_c=args.temp)
    est = float(a[np.argmax(p)])
    print(f"  [원점 확인] 0°에서 빔포밍 {est:+.0f}°", flush=True)
    return abs(est) <= CHECK_TOL


def main():
    ap = argparse.ArgumentParser(description="회전판 무작위 각도 자동 수집")
    ap.add_argument("--n", type=int, default=300, help="모을 개수")
    ap.add_argument("--range", type=float, default=60.0, help="±각도 범위")
    ap.add_argument("--place", required=True, help="장소 이름 (폴더 이름에 들어감)")
    ap.add_argument("--distance", type=float, default=1.0, help="스피커 거리 (m)")
    ap.add_argument("--temp", type=float, default=20.0, help="기온 (°C)")
    ap.add_argument("--sound", default="exp3_white")
    ap.add_argument("--speaker", default="A")
    ap.add_argument("--volume", type=float, default=0.3)
    ap.add_argument("--port", help="아두이노 포트 (없으면 자동)")
    ap.add_argument("--out", help="이어서 모을 폴더")
    ap.add_argument("--sim", action="store_true", help="장치 없이 점검")
    args = ap.parse_args()

    sys.path.insert(0, str(HERE.parent / "파이썬"))
    from turntable import Turntable

    folder = Path(args.out) if args.out else HERE / "수집" / f"{datetime.now():%Y%m%d}_{args.place}"
    folder.mkdir(parents=True, exist_ok=True)
    labels = folder / "labels.csv"
    done = 0
    if labels.exists():
        with open(labels, encoding="utf-8") as fp:
            done = sum(1 for _ in csv.DictReader(fp))
        print(f"{folder.name}에 {done}개가 이미 있어 이어서 모읍니다.")

    table = Turntable("sim" if args.sim else args.port, verbose=False)
    if args.sim:
        sio = FakeAudio(table)
    else:
        from sound_io import SoundIO
        sio = SoundIO()
        input("연필 0° 표시를 맞추고 스피커를 정면 1 m에 두었으면 Enter… ")
    table.enable(True)
    table.bench_origin()
    if not check_zero(table, sio, args):
        print("정면에서 빔포밍이 0°가 아니에요. 스피커 위치나 0° 표시를 다시 맞추세요.")
        return

    rng = np.random.default_rng()
    new = not labels.exists()
    fp = open(labels, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fp, FIELDS)
    if new:
        w.writeheader()
    t0 = time.time()
    try:
        for k in range(done + 1, done + args.n + 1):
            angle = round(float(rng.uniform(-args.range, args.range)), 2)
            table.goto(angle)
            time.sleep(0.5)                       # 흔들림이 멎을 때까지
            angle = table.status()["angle_deg"]   # 스텝 단위로 반올림된 실제 명령 각도
            rec, info = sio.play_and_record(args.sound, args.speaker, volume=args.volume)
            name = f"{k:04d}.wav"
            sio.save(rec, folder / name)
            w.writerow({"wav": name, "angle_deg": angle, "time": datetime.now().isoformat(timespec="seconds"),
                        "temp_c": args.temp, "place": args.place, "distance_m": args.distance,
                        "sound": args.sound, "peak": info["peak"]})
            fp.flush()
            left = (time.time() - t0) / (k - done) * (done + args.n - k)
            print(f"{k:4d}  {angle:+6.1f}°  peak {info['peak']:.2f}  (남은 시간 약 {left / 60:.0f}분)", flush=True)
            if info["peak"] >= 0.99:
                print("  ! 찌그러짐. 볼륨을 줄이세요.")
            if k % CHECK_EVERY == 0 and not check_zero(table, sio, args):
                print(f"원점이 {CHECK_TOL}°보다 어긋나 멈춥니다. 0° 표시를 확인하고 --out {folder}로 이어서 하세요.")
                break
    except KeyboardInterrupt:
        print("\n중단했어요. 같은 --out으로 다시 실행하면 이어서 모읍니다.")
    finally:
        fp.close()
        try:
            table.goto(0)
        finally:
            table.close()
    print(f"저장: {folder}")


if __name__ == "__main__":
    main()
