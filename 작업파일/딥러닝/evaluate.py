"""실험 3 비교: 같은 시험 녹음으로 지연-합 빔포밍, SRP-PHAT, MUSIC, 신경망의 오차를 잰다.

    python evaluate.py --model 결과/sim1/model.pt --sim 300 --seed 99
    python evaluate.py --model 결과/real1/model.pt --session 수집/20261127_도서관

시험 녹음은 학습에 쓰지 않은 세션이어야 한다. 결과는 결과 폴더에 표(csv)와 그림(png)으로 남는다.
"""

import argparse
import csv
from pathlib import Path

import numpy as np
import torch

import data
import gcc
from data import bf
from model import load

ANGLES = np.arange(-90, 90.25, 0.5)
BAND = (300, 4000)     # 빔포밍·MUSIC 계산 대역. 4 kHz 이하는 앨리어싱이 없다


def music(rec, temp_c=20.0, nfft=1024, band=BAND):
    """MUSIC(음원 1개 가정): 주파수마다 잡음 부분공간과 직교하는 방향을 찾고 주파수끼리 더한다."""
    x = np.asarray(rec, float)
    X = bf.stft(x - x.mean(axis=0), nfft)
    f = np.fft.rfftfreq(nfft, 1 / data.FS)
    sel = np.where((f >= band[0]) & (f <= band[1]))[0][::2]     # 계산을 줄이려고 한 칸 걸러
    tau = bf.arrival_delays(ANGLES, temp_c)                       # (A, 16)
    p = np.zeros(len(ANGLES))
    for k in sel:
        R = X[:, k, :].T @ X[:, k, :].conj() / len(X)            # (16, 16)
        _, V = np.linalg.eigh(R)
        En = V[:, :-1]                                           # 가장 큰 고유벡터 1개 빼고 = 잡음 부분공간
        a = np.exp(2j * np.pi * f[k] * tau)                      # (A, 16) = 도착 위상 벡터의 켤레
        p += 1 / np.maximum(np.sum(np.abs(a @ En) ** 2, axis=1), 1e-12)
    return p


def methods(rec, temp, net, device):
    out = {}
    a, p = bf.scan(rec, data.FS, angles=ANGLES, band=BAND, temp_c=temp)
    out["DAS"] = a[np.argmax(p)]
    a, p = gcc.srp_phat(rec, ANGLES, temp)
    out["SRP-PHAT"] = a[np.argmax(p)]
    out["MUSIC"] = ANGLES[np.argmax(music(rec, temp))]
    with torch.no_grad():
        x = torch.from_numpy(gcc.gcc_phat(rec)[None]).to(device)
        out["DNN"] = float(net(x)[0])
    return out


def main():
    ap = argparse.ArgumentParser(description="빔포밍·SRP-PHAT·MUSIC·신경망 비교")
    ap.add_argument("--model", required=True)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sim", type=int, metavar="개수")
    src.add_argument("--session", nargs="+")
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--range", type=float, default=60.0, help="이 각도 안의 녹음만 평가")
    args = ap.parse_args()

    net, ck = load(args.model)
    items = data.iter_sim(args.sim, args.seed) if args.sim else \
        (it for s in args.session for it in data.iter_session(s))
    rows = []
    for i, (rec, angle, temp, g) in enumerate(items, 1):
        if abs(angle) > args.range:
            continue
        est = methods(rec, temp, net, "cpu")
        rows.append({"group": g, "true": angle, **est})
        if i % 50 == 0:
            print(f"  {i}", flush=True)

    names = ["DAS", "SRP-PHAT", "MUSIC", "DNN"]
    true = np.array([r["true"] for r in rows])
    print(f"\n시험 {len(rows)}개 (모델 {args.model}, 학습 때 검증 평균오차 {ck['val_mae']:.2f}°)")
    print(f"{'방법':10s} {'평균오차':>8s} {'RMS':>8s} {'최대오차':>8s}")
    summary = []
    for n in names:
        e = np.abs(np.array([r[n] for r in rows]) - true)
        summary.append((n, e.mean(), np.sqrt((e ** 2).mean()), e.max()))
        print(f"{n:10s} {e.mean():7.2f}° {np.sqrt((e ** 2).mean()):7.2f}° {e.max():7.1f}°")

    out = Path(args.model).parent / ("eval_" + ("sim" if args.sim else "_".join(Path(s).name for s in args.session)))
    out.mkdir(exist_ok=True)
    with open(out / "each.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, ["group", "true"] + names)
        w.writeheader()
        w.writerows(rows)
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["method", "mae_deg", "rmse_deg", "max_deg"])
        w.writerows([(n, round(a, 3), round(b, 3), round(c, 2)) for n, a, b, c in summary])
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axs = plt.subplots(1, 4, figsize=(14, 3.6), sharey=True)
        for ax, (n, mae, _, mx) in zip(axs, summary):
            ax.scatter(true, np.array([r[n] for r in rows]) - true, s=6)
            ax.axhline(0, color="k", lw=0.5)
            ax.set_title(f"{n}  MAE {mae:.2f}°, max {mx:.1f}°")
            ax.set_xlabel("true angle (deg)")
            ax.grid(alpha=0.3)
        axs[0].set_ylabel("error (deg)")
        fig.tight_layout()
        fig.savefig(out / "error.png", dpi=120)
    except ImportError:
        pass
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
