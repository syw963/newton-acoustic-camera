"""1단계: 파이썬으로 회전판 돌리기.

    python step1_turntable.py --port sim          # 아두이노 없이 연습 (시뮬레이터)
    python step1_turntable.py                     # 진짜 아두이노 (포트 자동 찾기)
    python step1_turntable.py --port COM3         # Windows에서 포트 직접 지정
    python step1_turntable.py --demo              # 정해진 순서로 한 번 돌려 보기
    python step1_turntable.py --demo --bench      # 리밋 스위치 없이 (모터만 책상에 놓고)

직접 조작 모드에서 쓰는 명령 (시리얼 모니터와 같음):
    ?  상태   e1/e0 드라이버 켜기/끄기   h 원점 찾기   o 벤치 원점(스위치 없이)
    g-30 절대 각도로   m10 조금 움직이기   z 0° 정하기
    q  끝내기

12V를 켠 상태에서 모터 선을 꽂거나 빼지 마세요.
"""

import argparse
import time

from turntable import Turntable, TurntableError


def demo(t, bench=False):
    print("\n--- 데모: 원점 → -30° → 0° → +30° → 0° ---")
    print("상태:", t.status())
    t.enable(True)
    if bench:
        print("벤치 모드: 지금 위치를 0°로 정해요 (리밋 스위치 안 씀)")
        t.bench_origin()
    else:
        t.home()
    for a in (-30, 0, 30, 0):
        t0 = time.time()
        t.goto(a)
        print(f"   {a:+4d}° 도착 ({time.time() - t0:.1f}초)")
        time.sleep(0.5)
    print("상태:", t.status())
    t.enable(False)
    print("--- 끝 ---")


def interactive(t):
    print("\n명령을 입력하세요 (q로 끝내기). 예: ?  e1  h  g-30  g0  e0")
    while True:
        try:
            cmd = input("명령> ").strip().replace(" ", "")
        except (EOFError, KeyboardInterrupt):
            break
        if cmd in ("q", "quit", "exit"):
            break
        if not cmd:
            continue
        try:
            t.command(cmd, timeout=40)
            print("   ok")
        except TurntableError as e:
            print(f"   실패: {e}")


def main():
    ap = argparse.ArgumentParser(description="회전판 조작")
    ap.add_argument("--port", default=None, help="포트 이름 (비우면 자동, sim은 시뮬레이터)")
    ap.add_argument("--demo", action="store_true", help="정해진 순서로 한 번 돌려 보기")
    ap.add_argument("--bench", action="store_true", help="리밋 스위치 없이 지금 위치를 원점으로 (조립 전)")
    args = ap.parse_args()
    try:
        with Turntable(args.port) as t:
            if args.demo:
                demo(t, bench=args.bench)
            else:
                interactive(t)
            try:
                t.enable(False)  # 끝낼 때 모터 힘 빼기
            except TurntableError:
                pass
    except TurntableError as e:
        print(f"오류: {e}")


if __name__ == "__main__":
    main()
