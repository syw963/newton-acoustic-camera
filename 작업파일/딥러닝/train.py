"""신경망 학습. 노트북에서도, RunPod GPU에서도 같은 명령으로 돈다.

    python train.py --train 데이터/sim_train.npz --out 결과/sim1
    python train.py --train 데이터/real_train.npz --val 데이터/real_val.npz --init 결과/sim1/model.pt --out 결과/real1

--val이 없으면: 세션이 둘 이상이면 마지막 세션을 검증용으로 떼고, 하나뿐이면 무작위 10%를 뗀다
(무작위로 떼는 것은 가짜 녹음에서만 괜찮다. 실제 녹음은 다른 날·다른 곳 세션으로 검증한다).
--init은 가짜 녹음으로 먼저 학습한 모델에서 이어서 학습할 때 쓴다(사전 학습).
결과 폴더에 model.pt(가장 좋았던 것), log.csv, loss.png가 생긴다.
"""

import argparse
import csv
import time
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from model import DoaNet


def load_npz(paths):
    X, y, g = [], [], []
    for p in paths:
        d = np.load(p)
        X.append(d["X"].astype(np.float32))
        y.append(d["y"])
        g.append(d["group"])
    return np.concatenate(X), np.concatenate(y), np.concatenate(g)


def split(X, y, g, seed):
    groups = sorted(set(g))
    if len(groups) > 1:
        v = g == groups[-1]
        print(f"검증용 세션: {groups[-1]} ({v.sum()}개), 학습용: {groups[:-1]}")
    else:
        v = np.random.default_rng(seed).random(len(y)) < 0.1
        print(f"세션이 하나뿐이라 무작위 10%({v.sum()}개)를 검증용으로 뗌")
    return (X[~v], y[~v]), (X[v], y[v])


def pick_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def evaluate(model, loader, device):
    model.eval()
    err = []
    with torch.no_grad():
        for xb, yb in loader:
            err.append((model(xb.to(device)) - yb.to(device)).abs().cpu())
    e = torch.cat(err).numpy()
    return float(e.mean()), float(e.max())


def main():
    ap = argparse.ArgumentParser(description="GCC-PHAT → 각도 신경망 학습")
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--val", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--init", help="이어서 학습할 model.pt")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    X, y, g = load_npz(args.train)
    if args.val:
        tr, va = (X, y), load_npz(args.val)[:2]
    else:
        tr, va = split(X, y, g, args.seed)
    device = pick_device()
    print(f"학습 {len(tr[1])}개, 검증 {len(va[1])}개, 장치 {device}")

    def loader(d, shuffle):
        return DataLoader(TensorDataset(torch.from_numpy(d[0]), torch.from_numpy(d[1]).float()),
                          batch_size=args.batch, shuffle=shuffle)

    tr_dl, va_dl = loader(tr, True), loader(va, False)
    config = dict(pairs=X.shape[1])
    model = DoaNet(**config).to(device)
    if args.init:
        model.load_state_dict(torch.load(args.init, map_location=device)["state"])
        print(f"이어서 학습: {args.init}")
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.epochs)
    loss_fn = torch.nn.SmoothL1Loss(beta=1.0)   # 1° 넘는 오차는 절댓값처럼, 작은 오차는 제곱처럼

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = []
    best = float("inf")
    t0 = time.time()
    for ep in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for xb, yb in tr_dl:
            xb, yb = xb.to(device), yb.to(device)
            loss = loss_fn(model(xb), yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += loss.item() * len(yb)
        sched.step()
        tr_mae, _ = evaluate(model, tr_dl, device)
        va_mae, va_max = evaluate(model, va_dl, device)
        log.append((ep, total / len(tr[1]), tr_mae, va_mae, va_max))
        mark = ""
        if va_mae < best:
            best = va_mae
            torch.save({"state": model.state_dict(), "config": config, "epoch": ep, "val_mae": va_mae,
                        "train": [str(p) for p in args.train]}, out / "model.pt")
            mark = "  ← 저장"
        print(f"{ep:3d}  학습 평균오차 {tr_mae:5.2f}°  검증 평균오차 {va_mae:5.2f}°  최대 {va_max:5.1f}°"
              f"  ({time.time() - t0:.0f}초){mark}", flush=True)

    with open(out / "log.csv", "w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["epoch", "loss", "train_mae_deg", "val_mae_deg", "val_max_deg"])
        w.writerows(log)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        e = np.array(log)
        plt.figure(figsize=(6, 4))
        plt.plot(e[:, 0], e[:, 2], label="train")
        plt.plot(e[:, 0], e[:, 3], label="validation")
        plt.yscale("log")
        plt.xlabel("epoch")
        plt.ylabel("mean abs error (deg)")
        plt.legend()
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(out / "loss.png", dpi=120)
    except ImportError:
        pass
    print(f"끝. 가장 좋은 검증 평균오차 {best:.2f}° → {out / 'model.pt'}")


if __name__ == "__main__":
    main()
