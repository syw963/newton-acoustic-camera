"""5단계: 음향카메라. 카메라 화면 위에 소리 나는 곳을 색으로 겹쳐 보여 준다.

    python step5_acoustic_camera.py                # 카메라 0번
    python step5_acoustic_camera.py --camera 1     # 다른 카메라
    python step5_acoustic_camera.py --band 3000 5000 --hfov 80

카메라는 UMA-16 바로 위(또는 아래)에 마이크 면과 같은 쪽을 보게 단다. USB 단자는 아래.
화면 오른쪽 = 배열 뒤에서 볼 때 오른쪽 = +θ (beamform.py의 각도 약속과 같음).

키: q 끝, s 화면 저장(기록/acam_날짜.png), f 좌우 뒤집기, c 다음 카메라, +/- 보이는 범위(dB) 조절
시작하고 1.5초는 조용히 둔다(바닥 잡음 측정). 그보다 10 dB 이상 큰 소리가 날 때만 색을 칠한다.
"""

import argparse
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import audio
import beamform as bf
from uma_check import find_uma

HERE = Path(__file__).resolve().parent
FS = 48000
NFFT = 512
WIN_S = 0.3          # 한 번 계산에 쓰는 녹음 길이
GRID = (48, 27)      # 계산하는 칸 수 (가로, 세로). 화면 크기로 늘려 그린다


class Ring:
    """마지막 n 표본을 계속 담아 두는 16채널 녹음 버퍼."""

    def __init__(self, n, ch=16):
        self.buf = np.zeros((n, ch), np.float32)
        self.lock = threading.Lock()

    def push(self, x):
        with self.lock:
            k = len(x)
            self.buf = np.roll(self.buf, -k, axis=0)
            self.buf[-k:] = x

    def get(self):
        with self.lock:
            return self.buf.copy()


def pixel_directions(w, h, hfov_deg):
    """GRID 칸마다 그 칸 가운데 픽셀이 보는 방향 (가로각, 세로각). 핀홀 카메라로 계산."""
    f = (w / 2) / np.tan(np.radians(hfov_deg / 2))
    gx, gy = GRID
    u = (np.arange(gx) + 0.5) * w / gx - w / 2
    v = h / 2 - (np.arange(gy) + 0.5) * h / gy
    U, V = np.meshgrid(u, v)
    az = np.degrees(np.arctan2(U, f))
    el = np.degrees(np.arctan2(V, np.hypot(U, f)))
    return az, el


def make_steering(az, el, band, temp_c):
    f = np.fft.rfftfreq(NFFT, 1 / FS)
    sel = (f >= band[0]) & (f <= band[1])
    tau = bf.arrival_delays_2d(az, el, temp_c)                              # (D, 16)
    S = np.exp(2j * np.pi * f[sel][None, :, None] * tau[:, None, :])        # (D, F, 16)
    return sel, S


def power_map(x, sel, S):
    """지연-합 세기. 교차 스펙트럼 행렬 R(f)를 먼저 구해 계산을 줄인다. (D,), 띠 전체 세기."""
    X = bf.stft(x - x.mean(axis=0), NFFT)[:, sel, :]                        # (T, F, 16)
    R = np.einsum("tfm,tfn->fmn", X, X.conj()) / len(X)                    # (F, 16, 16)
    p = np.einsum("dfm,fmn,dfn->d", S, R, S.conj(), optimize=True).real
    level = float(np.real(np.einsum("fmm->", R)))
    return np.maximum(p, 1e-20), level


def open_camera(idx):
    cap = cv2.VideoCapture(idx)
    if not cap.isOpened():
        return None
    ok, _ = cap.read()
    if not ok:
        cap.release()
        return None
    return cap


def main():
    ap = argparse.ArgumentParser(description="음향카메라: 카메라 화면에 소리 지도 겹치기")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hfov", type=float, default=80.0, help="카메라 가로 화각 (°)")
    ap.add_argument("--band", type=float, nargs=2, default=(1000, 4000), metavar=("낮은Hz", "높은Hz"))
    ap.add_argument("--temp", type=float, default=20.0)
    ap.add_argument("--range", type=float, default=6.0, help="최대에서 몇 dB 아래까지 칠할지")
    ap.add_argument("--flip", action="store_true", help="화면 좌우 뒤집기")
    args = ap.parse_args()

    if not audio.available():
        print(audio.why_unavailable())
        return
    idx, d = find_uma()
    if idx is None:
        print("UMA-16을 찾지 못했어요. uma_check.py로 먼저 확인하세요.")
        return
    cam_idx = args.camera
    cap = open_camera(cam_idx)
    if cap is None:
        print(f"카메라 {cam_idx}번을 열 수 없어요. --camera 번호를 바꾸거나, Mac이면 "
              "시스템 설정 > 개인정보 보호 및 보안 > 카메라에서 터미널(VS Code)을 켜세요.")
        return

    ring = Ring(int(WIN_S * FS))
    stream = audio.sd.InputStream(device=idx, channels=16, samplerate=FS, dtype="float32",
                                  blocksize=1024, callback=lambda x, n, t, s: ring.push(x))
    stream.start()

    ok, frame = cap.read()
    h, w = frame.shape[:2]
    az, el = pixel_directions(w, h, args.hfov)
    sel, S = make_steering(az, el, args.band, args.temp)
    print(f"카메라 {cam_idx}번 {w}×{h}, 화각 {args.hfov:.0f}°, 대역 {args.band[0]:.0f}~{args.band[1]:.0f} Hz")
    print("1.5초 동안 조용히 해 주세요 (바닥 잡음 측정)… 그다음 q로 끝, s로 저장")

    t0 = time.time()
    floor_levels = []
    floor = None
    smooth = None
    flip = args.flip
    rng = args.range
    win = "음향카메라 (q 끝, s 저장)"
    fails = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            # USB가 잠깐 끊기거나 카메라를 옮길 때 생김. 1초쯤 기다렸다가 다시 열어 본다
            fails += 1
            if fails % 30 == 0:
                print("카메라 영상이 끊겼어요. 다시 열어 봅니다…", flush=True)
                cap.release()
                cap = open_camera(cam_idx) or cap
            if fails > 150:
                print("카메라 영상을 5초 넘게 받지 못해 끝냅니다. USB 연결을 확인하세요.")
                break
            time.sleep(0.03)
            continue
        fails = 0
        if flip:
            frame = cv2.flip(frame, 1)
        p, level = power_map(ring.get(), sel, S)
        level_db = 10 * np.log10(level + 1e-20)
        if floor is None:
            floor_levels.append(level_db)
            if time.time() - t0 > 1.5:
                floor = float(np.median(floor_levels))
            cv2.putText(frame, "Measuring noise floor... keep quiet", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        else:
            smooth = p if smooth is None else 0.5 * smooth + 0.5 * p
            loud = level_db - floor
            if loud > 10:
                db = 10 * np.log10(smooth / smooth.max()).reshape(el.shape)
                a = np.clip(1 + db / rng, 0, 1)                             # 최대 1, rng dB 아래 0
                a_big = cv2.resize(a.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
                a_big = np.clip(a_big, 0, 1)
                color = cv2.applyColorMap((a_big * 255).astype(np.uint8), cv2.COLORMAP_JET)
                alpha = (0.6 * a_big)[..., None]
                frame = (frame * (1 - alpha) + color * alpha).astype(np.uint8)
                k = int(np.argmax(smooth))
                ky, kx = np.unravel_index(k, el.shape)
                px, py = int((kx + 0.5) * w / GRID[0]), int((ky + 0.5) * h / GRID[1])
                cv2.drawMarker(frame, (px, py), (255, 255, 255), cv2.MARKER_CROSS, 30, 2)
                txt = f"az {az[ky, kx]:+.0f} deg, el {el[ky, kx]:+.0f} deg"
                cv2.putText(frame, txt, (px + 12, py - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"level +{max(loud, 0):.0f} dB  range {rng:.0f} dB  band {args.band[0]:.0f}-{args.band[1]:.0f} Hz"
                        + ("  [flip]" if flip else ""), (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow(win, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        if key == ord("s"):
            out = HERE / "기록" / f"acam_{datetime.now():%Y%m%d_%H%M%S}.png"
            out.parent.mkdir(exist_ok=True)
            cv2.imwrite(str(out), frame)
            print(f"저장: {out}")
        if key == ord("f"):
            flip = not flip
        if key in (ord("+"), ord("=")):
            rng = min(rng + 1, 20)
        if key == ord("-"):
            rng = max(rng - 1, 1)
        if key == ord("c"):
            for j in range(1, 5):
                nxt = (cam_idx + j) % 5
                c2 = open_camera(nxt)
                if c2 is not None:
                    cap.release()
                    cap, cam_idx = c2, nxt
                    ok, frame = cap.read()
                    h, w = frame.shape[:2]
                    az, el = pixel_directions(w, h, args.hfov)
                    sel, S = make_steering(az, el, args.band, args.temp)
                    smooth = None
                    print(f"카메라 {cam_idx}번으로 바꿈 ({w}×{h})")
                    break

    stream.stop()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
