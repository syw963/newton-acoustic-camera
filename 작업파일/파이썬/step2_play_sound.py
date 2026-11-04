"""2단계: 스피커 A·B로 소리 내기.

    python step2_play_sound.py                         # 채널 확인 wav (A 낮은 소리 → B 높은 소리)
    python step2_play_sound.py --tone 1000 --side A    # 1 kHz 순음을 스피커 A로 1초
    python step2_play_sound.py --tone 2000 --side B --seconds 2
    python step2_play_sound.py --file ../신호/signals/exp1_white.wav --side A

처음에는 앰프 볼륨을 최소로 두고, --volume을 낮게(기본 0.3) 시작하세요.
노트북의 소리 향상·공간 음향 기능은 꺼 두세요(배선_작업순서.md 4단계).
"""

import argparse
from pathlib import Path

import audio

HERE = Path(__file__).resolve().parent
DEFAULT_WAV = HERE.parent / "신호" / "signals" / "00_채널확인.wav"


def main():
    ap = argparse.ArgumentParser(description="스피커 A·B 소리 시험")
    ap.add_argument("--file", default=None, help="재생할 wav (기본: 00_채널확인.wav)")
    ap.add_argument("--tone", type=float, default=None, help="순음 주파수 Hz (파일 대신)")
    ap.add_argument("--seconds", type=float, default=1.0, help="순음 길이")
    ap.add_argument("--side", default="A", choices=["A", "B", "AB", "a", "b", "ab"], help="모노 소리를 보낼 스피커")
    ap.add_argument("--volume", type=float, default=0.3, help="0~1, 처음엔 낮게")
    ap.add_argument("--device", default=None, help="출력 장치 번호 (step0에서 확인, 비우면 기본 출력)")
    args = ap.parse_args()

    if not audio.available():
        print(audio.why_unavailable())
        return
    device = int(args.device) if args.device and args.device.isdigit() else args.device

    if args.tone:
        x, fs = audio.tone(args.tone, args.seconds), audio.FS
        print(f"{args.tone:.0f} Hz 순음 {args.seconds}초 → 스피커 {args.side.upper()}")
    else:
        import soundfile as sf
        path = Path(args.file) if args.file else DEFAULT_WAV
        if not path.exists():
            print(f"파일이 없어요: {path}")
            return
        x, fs = sf.read(str(path), dtype="float32")
        kind = "스테레오(파일에 적힌 대로 A·B)" if x.ndim == 2 and x.shape[1] == 2 else f"모노 → 스피커 {args.side.upper()}"
        print(f"{path.name}  {len(x) / fs:.1f}초, {fs} Hz, {kind}")
        if path.name.startswith("00_"):
            print("  기대: 스피커 A에서 낮은 소리(1 kHz) → 쉼 → 스피커 B에서 높은 소리(2 kHz)")
    audio.play(x, side=args.side, fs=fs, volume=args.volume, device=device)
    print("끝. 반대로 들리면 앰프 입력이나 출력의 L·R 선을 바꾸세요.")


if __name__ == "__main__":
    main()
