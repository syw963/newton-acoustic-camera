"""0단계: 노트북이 장치를 알아보는지 확인한다.

    python step0_check_devices.py

- 파이썬 버전과 필요한 패키지
- 시리얼 포트 (아두이노 후보 표시)
- 오디오 장치 (기본 출력, 16채널 입력 = UMA-16 후보 표시)
"""

import platform
import sys

print("=" * 60)
print(f"파이썬 {platform.python_version()} · {platform.system()} {platform.release()}")
if sys.version_info < (3, 9):
    print("  ! 파이썬 3.9 이상이 필요해요")

missing = []
for mod, pip_name in [("numpy", "numpy"), ("serial", "pyserial"), ("sounddevice", "sounddevice"), ("soundfile", "soundfile")]:
    try:
        __import__(mod)
        print(f"  [있음] {pip_name}")
    except Exception as e:
        missing.append(pip_name)
        print(f"  [없음] {pip_name}  ({e.__class__.__name__})")
if missing:
    print("\n  → pip install -r requirements.txt 를 실행하세요\n")

print("=" * 60)
print("시리얼 포트")
try:
    from serial.tools import list_ports
    from turntable import KNOWN_VIDS

    ports = list(list_ports.comports())
    if not ports:
        print("  (없음) 아두이노 USB 선을 꽂았는지 확인하세요")
    for p in ports:
        mark = ""
        if p.vid in KNOWN_VIDS:
            mark = f"  ← 아두이노 후보 ({KNOWN_VIDS[p.vid]})"
        print(f"  {p.device:28s} {p.description}{mark}")
except ImportError:
    print("  pyserial이 없어 확인할 수 없어요")

print("=" * 60)
print("오디오 장치")
import audio

if not audio.available():
    print("  " + audio.why_unavailable())
else:
    for i, name, nin, nout, is_default in audio.list_devices():
        tags = []
        if is_default:
            tags.append("기본 출력 ← 스피커는 여기로 나가요")
        if nin >= 16:
            tags.append("16채널 입력 ← UMA-16 후보")
        print(f"  {i:3d}  입력 {nin:2d} / 출력 {nout:2d}  {name}" + (f"   [{', '.join(tags)}]" if tags else ""))
print("=" * 60)
print("다음: python step1_turntable.py --port sim   (아두이노 없이 연습)")
