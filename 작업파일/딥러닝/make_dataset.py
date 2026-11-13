"""녹음 → 학습용 특징 파일(npz).

    python make_dataset.py --sim 5000 --out 데이터/sim_train.npz            # 가짜 녹음
    python make_dataset.py --sim 500 --seed 1 --out 데이터/sim_test.npz
    python make_dataset.py --session 수집/20261120_과학실 수집/20261121_과학실 --out 데이터/real_train.npz

npz 안: X (개수, 120, 65) GCC-PHAT, y (개수,) 정답 각도, group (개수,) 세션 이름, temp (개수,) 기온.
녹음 wav는 크지만 npz는 작다(1000개에 약 15 MB). RunPod에는 npz만 올리면 된다.
"""

import argparse
import time
from pathlib import Path

import numpy as np

import data
import gcc


def main():
    ap = argparse.ArgumentParser(description="녹음을 GCC-PHAT 특징 npz로")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sim", type=int, metavar="개수", help="가짜 녹음 개수")
    src.add_argument("--session", nargs="+", help="collect.py가 만든 폴더들")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.sim:
        items, total = data.iter_sim(args.sim, args.seed), args.sim
    else:
        items = (it for s in args.session for it in data.iter_session(s))
        total = None
    X, y, group, temp = [], [], [], []
    t0 = time.time()
    for i, (rec, angle, t, g) in enumerate(items, 1):
        X.append(gcc.gcc_phat(rec))
        y.append(angle)
        group.append(g)
        temp.append(t)
        if i % 200 == 0:
            print(f"  {i}" + (f"/{total}" if total else "") + f"  ({time.time() - t0:.0f}초)", flush=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, X=np.stack(X).astype(np.float16), y=np.array(y, np.float32),
                        group=np.array(group), temp=np.array(temp, np.float32))
    print(f"저장: {out}  ({len(y)}개, 각도 {min(y):+.1f}~{max(y):+.1f}°, 세션 {sorted(set(group))})")


if __name__ == "__main__":
    main()
