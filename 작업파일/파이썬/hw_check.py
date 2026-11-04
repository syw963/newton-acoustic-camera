"""실제 하드웨어 점검: 하나씩 움직여 보고, 눈으로 확인한 답을 받아 기록한다.

    python hw_check.py                 # 아두이노 자동 찾기
    python hw_check.py --port COM5     # 포트 직접 지정
    python hw_check.py --port sim      # 연습 (답은 직접 입력)

질문에는 y(예) / n(아니오) / s(건너뛰기)로 답한다. 끝나면 기록/hw_check_날짜.md 에 결과가 남는다.
배선 순서와 Vref 조정은 문서/배선_작업순서.md 1~2단계를 먼저 끝낸 뒤에 한다.
"""

import argparse
import platform
import time
from datetime import datetime
from pathlib import Path

import audio
from turntable import Turntable, TurntableError

HERE = Path(__file__).resolve().parent
CHANNEL_WAV = HERE.parent / "신호" / "signals" / "00_채널확인.wav"

results = []  # (항목, 결과, 메모)


def ask(q, choices="yns"):
    hint = {"y": "y=예", "n": "n=아니오", "s": "s=건너뛰기", "b": "b=떨기만 함"}
    opts = " / ".join(hint[c] for c in choices)
    while True:
        try:
            a = input(f"  ? {q} [{opts}] ").strip().lower()
        except EOFError:
            return "s"
        if a[:1] in choices:
            return a[:1]


def record(item, ok, memo=""):
    mark = {True: "통과", False: "실패", None: "건너뜀"}[ok]
    results.append((item, mark, memo))
    print(f"  → {mark}" + (f": {memo}" if memo else ""))


def head(n, title):
    print(f"\n[{n}] {title}")


def main():
    ap = argparse.ArgumentParser(description="하드웨어 점검")
    ap.add_argument("--port", default=None)
    ap.add_argument("--volume", type=float, default=0.3)
    args = ap.parse_args()

    print("=" * 60)
    print("하드웨어 점검. 시작 전에 확인하세요:")
    print("  - 12V가 꺼진 상태에서 모터 선을 꽂았다 (켠 채로 꽂거나 빼면 A4988이 망가짐)")
    print("  - A4988 Vref를 맞췄다 (배선_작업순서.md 2단계, 0.9 A 기준)")
    print("  - 아두이노 IDE의 시리얼 모니터를 닫았다")
    print("  - 모터 축에 테이프 깃발을 붙여 도는 방향과 각도를 볼 수 있게 했다")
    if ask("준비됐나요?", "yn") != "y":
        print("준비한 뒤 다시 실행하세요.")
        return

    try:
        t = Turntable(args.port, verbose=False)
    except TurntableError as e:
        print(f"연결 실패: {e}")
        return

    try:
        # 1. 연결
        head(1, "연결과 상태")
        st = t.status()
        print(f"  포트 {t.port}, 상태 {st}")
        record("아두이노 연결", True, f"{t.port}")

        # 2. 드라이버
        head(2, "모터 드라이버 켜기 (12V 어댑터를 지금 꽂으세요)")
        t.enable(True)
        a = ask("모터 축을 손가락으로 돌려 보면 뻑뻑하게 버티나요?")
        record("드라이버 켜짐(유지 토크)", {"y": True, "n": False}.get(a),
               "" if a != "n" else "12V 연결, 드라이버 방향(EN 핀), Vref가 0에 가까운지 확인")

        # 3. 방향
        head(3, "방향: 10° 돌리기 (m10)")
        t.nudge(10)
        a = ask("위에서 볼 때 반시계 방향으로 조금(10°) 돌았나요?", "ynbs")
        if a == "y":
            record("회전 방향", True, "+ = 반시계")
        elif a == "n":
            record("회전 방향", False, "시계 방향이면 turntable.ino의 DIR_INVERT를 true로 바꿔 다시 업로드")
        elif a == "b":
            record("회전 방향", False, "떨기만 함: 12V 끄고 한 코일 쌍의 두 선을 바꿔 꽂기 (배선 2단계)")
            raise TurntableError("모터가 돌지 않아 여기서 멈춰요. 고친 뒤 다시 실행하세요")
        else:
            record("회전 방향", None)
        t.nudge(-10)

        # 4. 원점과 왕복
        head(4, "원점과 왕복 이동")
        a = ask("회전판이 조립돼 있고 리밋 스위치가 −70° 자리에 달려 있나요? (n이면 벤치 원점 사용)")
        bench = a != "y"
        if bench:
            try:
                t.bench_origin()
                print("  벤치 원점: 지금 위치를 0°로 정했어요")
            except TurntableError as e:
                record("벤치 원점", False, f"{e} → 작업파일/아두이노/turntable.ino 최신본을 업로드하세요")
                raise
        else:
            t0 = time.time()
            t.home()
            record("원점 찾기(h)", True, f"{time.time() - t0:.1f}초")
        times = []
        for g in (-60, 60, 0):
            t0 = time.time()
            t.goto(g)
            times.append(f"{g:+d}°:{time.time() - t0:.1f}s")
        print("  이동 시간 " + ", ".join(times))
        a = ask("−60° → +60° → 0°를 돌고 깃발이 처음 자리로 돌아왔나요?")
        record("왕복 후 제자리", {"y": True, "n": False}.get(a),
               ", ".join(times) if a != "n" else "스텝을 잃음: Vref를 조금 올리거나 turntable.ino의 PERIOD_FAST를 키움")

        # 5. 리밋 스위치
        head(5, "리밋 스위치")
        a = ask("리밋 스위치를 쉴드 X− 단자에 연결했나요?")
        if a == "y":
            before = t.status().get("limit")
            print("  10초 동안 스위치를 2~3번 눌렀다 떼세요...")
            lines = t.command("w", timeout=15)
            presses = sum(1 for ln in lines if ln == "눌림")
            ok = before == "떨어짐" and presses > 0
            memo = f"누르기 전 {before}, 눌림 {presses}회"
            if before != "떨어짐":
                memo += " → 항상 눌림이면 NO 대신 NC에 연결했거나 신호·GND 핀이 바뀜"
            elif presses == 0:
                memo += " → 납땜, COM·NO 단자, X− 단자 핀 확인"
            record("리밋 스위치", ok, memo)
        else:
            record("리밋 스위치", None, "아직 연결 안 함")

        # 6. 소리
        head(6, "스피커 A·B (앰프 볼륨을 작게)")
        if not audio.available():
            record("스피커 채널", None, audio.why_unavailable())
        elif ask("앰프와 스피커를 연결하고 노트북 이어폰 단자에 꽂았나요?") == "y":
            import soundfile as sf
            x, fs = sf.read(str(CHANNEL_WAV), dtype="float32")
            print("  재생 중: A에서 낮은 소리 → 쉼 → B에서 높은 소리가 나와야 해요")
            audio.play(x, fs=fs, volume=args.volume)
            a = ask("A에서 낮은 소리, B에서 높은 소리 순서로 들렸나요?")
            record("스피커 채널", {"y": True, "n": False}.get(a),
                   "" if a != "n" else "반대면 앰프 L·R 선을 바꿈. 한쪽만 나오면 3.5mm 선 L·R·G와 노트북 모노 설정 확인")
        else:
            record("스피커 채널", None, "아직 연결 안 함")

    except TurntableError as e:
        print(f"\n중단: {e}")
        record("중단", False, str(e))
    except KeyboardInterrupt:
        print("\n사용자가 중단함")
    finally:
        try:
            if t.status().get("homed") == "yes":
                t.goto(0)  # 끝낼 때 0°로 돌려 둠
        except Exception:
            pass
        try:
            t.enable(False)
        except Exception:
            pass
        t.close()

    # 기록
    out = HERE / "기록"
    out.mkdir(exist_ok=True)
    path = out / f"hw_check_{datetime.now():%Y%m%d_%H%M%S}.md"
    lines = [f"# 하드웨어 점검 {datetime.now():%Y-%m-%d %H:%M}", "",
             f"- 노트북: {platform.system()} {platform.release()}, 파이썬 {platform.python_version()}",
             f"- 포트: {args.port or '자동'}", "",
             "| 항목 | 결과 | 메모 |", "|---|---|---|"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in results]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "=" * 60)
    for a, b, c in results:
        print(f"  {b:4s}  {a}" + (f"  ({c})" if c else ""))
    print(f"\n기록 저장: {path}")


if __name__ == "__main__":
    main()
