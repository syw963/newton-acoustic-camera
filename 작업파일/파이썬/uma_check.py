"""UMA-16 점검: 장치 정보, 16채널 실시간 레벨, 채널 위치표 만들기.

    python uma_check.py              # 장치 정보 + 16채널 레벨 (Ctrl+C로 끝)
    python uma_check.py --seconds 5  # 5초만 보고 끝
    python uma_check.py --map        # 마이크를 하나씩 긁어 채널 위치표 만들기

--map 순서: 마이크 면을 마주 보고(스피커 쪽에서 배열을 볼 때) 위쪽 행부터,
각 행은 왼쪽에서 오른쪽으로 마이크 16개를 차례로 손톱으로 1~2초 긁는다.
한 번 긁을 때마다 가장 크게 들은 채널을 그 위치에 적고, 끝나면 기록/uma_map_날짜.md 에 남긴다.
말소리처럼 모든 채널에 비슷하게 들어온 소리는 무시하고 같은 위치를 다시 긁으라고 알려 준다.
"""

import argparse
import platform
import queue
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import audio

sd = audio.sd
HERE = Path(__file__).resolve().parent
FS = audio.FS
CHANNELS = 16
PITCH_MM = 42  # 마이크 간격 (설계: D = 4 × 42 = 168mm)
BLOCK_S = 0.02


def find_uma():
    """이름에 UMA16이 들어간 입력 장치, 없으면 16채널 이상 입력 장치."""
    devs = list(enumerate(sd.query_devices()))
    for i, d in devs:
        name = d["name"].upper().replace("-", "")
        if "UMA16" in name and d["max_input_channels"] >= CHANNELS:
            return i, d
    for i, d in devs:
        if d["max_input_channels"] >= CHANNELS:
            return i, d
    return None, None


def show_info(idx, d):
    host = sd.query_hostapis(d["hostapi"])["name"]
    print("=" * 60)
    print(f"장치 {idx}: {d['name']}  ({host}, {platform.system()})")
    print(f"  입력 {d['max_input_channels']} / 출력 {d['max_output_channels']}")
    print(f"  기본 표본화 주파수 {d['default_samplerate']:.0f} Hz")
    try:
        sd.check_input_settings(device=idx, channels=CHANNELS, samplerate=FS, dtype="float32")
        ok48 = True
        print(f"  {FS} Hz · {CHANNELS}채널 입력: 가능")
    except Exception as e:
        ok48 = False
        print(f"  {FS} Hz · {CHANNELS}채널 입력: 불가 ({e})")
    print("=" * 60)
    return host, ok48


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-10))


def open_stream(idx, q):
    def cb(indata, frames, t, status):
        q.put(np.sqrt(np.mean(indata.astype(np.float64) ** 2, axis=0)))

    return sd.InputStream(device=idx, channels=CHANNELS, samplerate=FS, dtype="float32",
                          blocksize=int(BLOCK_S * FS), callback=cb)


def meter(idx, seconds):
    """0.1초마다 채널별 레벨(dBFS)을 막대로 보여 준다."""
    q = queue.Queue()
    tty = sys.stdout.isatty()
    lo, hi, width = -90.0, 0.0, 36
    print("16채널 레벨 (dBFS). 마이크를 하나씩 긁어 보면 해당 채널 막대가 길어져요. Ctrl+C로 끝.")
    t0 = time.time()
    peak_all = np.zeros(CHANNELS)
    first = True
    lines = []
    with open_stream(idx, q):
        try:
            while seconds is None or time.time() - t0 < seconds:
                time.sleep(0.1)
                blocks = []
                while not q.empty():
                    blocks.append(q.get())
                if not blocks:
                    continue
                rms = np.sqrt(np.mean(np.square(blocks), axis=0))
                peak_all = np.maximum(peak_all, rms)
                lines = []
                for ch in range(CHANNELS):
                    v = db(rms[ch])
                    n = int(np.clip((v - lo) / (hi - lo), 0, 1) * width)
                    lines.append(f"  ch{ch + 1:2d} {v:6.1f} |{'#' * n}{' ' * (width - n)}|")
                if tty:
                    if not first:
                        sys.stdout.write(f"\x1b[{CHANNELS}A")
                    sys.stdout.write("\n".join(lines) + "\n")
                    sys.stdout.flush()
                    first = False
        except KeyboardInterrupt:
            pass
    if not tty and lines:
        print("\n".join(lines))
    if np.all(peak_all == 0):
        print("\n! 모든 채널이 정확히 0이에요. Mac이면 시스템 설정 > 개인정보 보호 및 보안 > 마이크에서")
        print("  이 프로그램을 실행한 앱(터미널, VS Code)을 켜고 다시 실행하세요.")
    else:
        dead = [ch + 1 for ch in range(CHANNELS) if db(peak_all[ch]) < -85]
        if dead:
            print(f"\n! 거의 소리가 없는 채널: {dead}")


def position_name(k):
    r, c = divmod(k, 4)
    return f"{r + 1}행 {c + 1}열"


def coord(k):
    """위치 번호(0~15) → 배열 중심 기준 (x, y) mm. x는 오른쪽, y는 위쪽이 +."""
    r, c = divmod(k, 4)
    return (c - 1.5) * PITCH_MM, (1.5 - r) * PITCH_MM


def map_channels(idx, d, host, thresh_db, margin_db):
    q = queue.Queue()
    pos_to_ch = [None] * CHANNELS
    margins = [None] * CHANNELS
    notes = []
    with open_stream(idx, q):
        print("2초 동안 조용히 해 주세요. 바닥 잡음을 잽니다…", flush=True)
        time.sleep(2.0)
        blocks = []
        while not q.empty():
            blocks.append(q.get())
        floor = np.median(blocks, axis=0)
        floor_db = db(floor)
        print(f"  바닥 잡음 {floor_db.min():.1f} ~ {floor_db.max():.1f} dBFS", flush=True)
        if np.all(floor == 0):
            print("! 모든 채널이 0이에요. 마이크 권한을 확인하세요(Mac: 개인정보 보호 및 보안 > 마이크).")
            return None

        k = 0
        print(f"\n위치 1 ({position_name(0)})을 긁으세요.", flush=True)
        while k < CHANNELS:
            # 소리가 시작될 때까지 기다림
            x = q.get()
            if np.max(db(x) - floor_db) < thresh_db:
                continue
            energy = x ** 2
            quiet = 0
            while quiet < int(0.5 / BLOCK_S):  # 0.5초 조용하면 한 번 끝
                x = q.get()
                energy += x ** 2
                quiet = quiet + 1 if np.max(db(x) - floor_db) < 10 else 0
            order = np.argsort(energy)[::-1]
            ch, second = order[0], order[1]
            m = 10 * np.log10(energy[ch] / max(energy[second], 1e-20))
            if m < margin_db:
                print(f"  ? 여러 채널에 비슷하게 들어왔어요 (ch{ch + 1}과 ch{second + 1} 차이 {m:.1f} dB). "
                      f"위치 {k + 1}을 마이크 구멍 바로 위에서 다시 긁으세요.", flush=True)
                continue
            if ch in pos_to_ch:
                prev = pos_to_ch.index(ch)
                print(f"  ? ch{ch + 1}은 이미 위치 {prev + 1}({position_name(prev)})에 있어요. "
                      f"위치 {k + 1}을 다시 긁으세요.", flush=True)
                notes.append(f"위치 {k + 1}에서 ch{ch + 1}이 다시 잡혀 다시 긁음")
                continue
            pos_to_ch[k] = int(ch)
            margins[k] = m
            print(f"  위치 {k + 1:2d} ({position_name(k)}) → ch{ch + 1:2d}   (2위 ch{second + 1}보다 {m:.1f} dB 큼)",
                  flush=True)
            k += 1
            if k < CHANNELS:
                print(f"위치 {k + 1} ({position_name(k)})을 긁으세요.", flush=True)

    return save_map(d, host, floor_db, pos_to_ch, margins, notes)


def save_map(d, host, floor_db, pos_to_ch, margins, notes):
    now = datetime.now()
    out = HERE / "기록"
    out.mkdir(exist_ok=True)
    path = out / f"uma_map_{now:%Y%m%d_%H%M%S}.md"
    L = [
        f"# UMA-16 채널 위치표 ({now:%Y-%m-%d %H:%M})",
        "",
        f"- 장치: {d['name']} ({host}, {platform.system()}), {FS} Hz, {CHANNELS}채널",
        f"- 바닥 잡음: {floor_db.min():.1f} ~ {floor_db.max():.1f} dBFS",
        "- 방법: `python uma_check.py --map`. 마이크를 하나씩 긁고 가장 큰 에너지가 들어온 채널을 적음.",
        "- 위치 기준: 마이크 면을 마주 보고(스피커 쪽에서 배열을 볼 때) 위쪽이 1행, 왼쪽이 1열.",
        f"- 좌표: 배열 중심이 원점, x는 오른쪽 +, y는 위쪽 +, 간격 {PITCH_MM}mm.",
        "",
        "## 4×4 배치 (칸 안은 채널 번호)",
        "",
        "| | 1열 | 2열 | 3열 | 4열 |",
        "|---|---|---|---|---|",
    ]
    for r in range(4):
        L.append(f"| {r + 1}행 | " + " | ".join(f"ch{pos_to_ch[r * 4 + c] + 1}" for c in range(4)) + " |")
    L += ["", "## 채널별 좌표", "", "| 채널 | 위치 | x (mm) | y (mm) | 2위와 차이 (dB) |", "|---|---|---|---|---|"]
    ch_to_pos = {ch: k for k, ch in enumerate(pos_to_ch)}
    for ch in range(CHANNELS):
        k = ch_to_pos[ch]
        x, y = coord(k)
        L.append(f"| {ch + 1} | {position_name(k)} | {x:+.0f} | {y:+.0f} | {margins[k]:.1f} |")
    L += ["", "파이썬 배열 (채널 순서, 0번 = ch1):", "", "```python",
          "MIC_XY_MM = [" + ", ".join(f"({coord(ch_to_pos[ch])[0]:+.0f}, {coord(ch_to_pos[ch])[1]:+.0f})"
                                    for ch in range(CHANNELS)) + "]",
          "```"]
    if notes:
        L += ["", "## 메모", ""] + [f"- {n}" for n in notes]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n기록 저장: {path}")
    return path


def main():
    ap = argparse.ArgumentParser(description="UMA-16 점검")
    ap.add_argument("--map", action="store_true", help="마이크를 하나씩 긁어 채널 위치표 만들기")
    ap.add_argument("--seconds", type=float, default=None, help="레벨 보기 시간 (기본: Ctrl+C까지)")
    ap.add_argument("--thresh", type=float, default=25.0, help="긁기로 볼 크기 (바닥 잡음보다 dB)")
    ap.add_argument("--margin", type=float, default=6.0, help="1위 채널이 2위보다 커야 하는 dB")
    args = ap.parse_args()

    if not audio.available():
        print(audio.why_unavailable())
        return
    idx, d = find_uma()
    if idx is None:
        print("16채널 입력 장치를 찾지 못했어요. USB 허브와 UMA-16 연결을 확인하세요.")
        for i, name, nin, nout, _ in audio.list_devices():
            print(f"  {i:3d}  입력 {nin:2d} / 출력 {nout:2d}  {name}")
        return
    host, ok48 = show_info(idx, d)
    if not ok48:
        print("48 kHz로 열 수 없어요. Mac은 오디오 MIDI 설정, Windows는 소리 설정에서 48000 Hz로 바꾸세요.")
        return
    if args.map:
        map_channels(idx, d, host, args.thresh, args.margin)
    else:
        meter(idx, args.seconds)


if __name__ == "__main__":
    main()
