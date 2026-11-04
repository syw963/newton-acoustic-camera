# 파이썬: 하드웨어 조작 첫걸음

노트북에서 파이썬으로 회전판(아두이노)을 돌리고 스피커 A·B로 소리를 낸다. UMA-16 녹음과 빔포밍은 다음 단계에서 이 위에 붙인다.

## 설치 (한 번만)

파이썬 3.9 이상이 필요하다. 이 폴더(`작업파일/파이썬`)에서 실행한다.

**Windows (PowerShell)**

```
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Mac (터미널)**

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

다음에 다시 쓸 때는 `activate` 줄만 다시 실행한다.

## 단계

| 파일 | 하는 일 | 아두이노 없이 |
|---|---|---|
| `step0_check_devices.py` | 패키지, 시리얼 포트(아두이노 후보), 오디오 장치(기본 출력, 16채널 입력) 확인 | 됨 |
| `step1_turntable.py` | 회전판 직접 조작(명령 입력) 또는 `--demo` | `--port sim` |
| `step2_play_sound.py` | 채널 확인 wav, 순음을 스피커 A·B로 | 소리만 필요 |
| `step3_rotate_and_play.py` | 돌리기 → 기다리기 → 소리 반복, `기록/`에 csv 저장 | `--port sim --no-sound` |
| `hw_check.py` | 실제 하드웨어를 하나씩 움직이며 묻고 기록 | `--port sim`(답은 직접 입력) |

```
python step0_check_devices.py
python step1_turntable.py --port sim --demo
python step2_play_sound.py
python step3_rotate_and_play.py --port sim --no-sound
```

## 실제 하드웨어로 하기

1. **스케치 업로드**: 아두이노 IDE 2에서 `작업파일/아두이노/turntable/turntable.ino`를 열고, 보드는 Arduino Uno, 포트는 아두이노 포트를 고른 뒤 업로드한다. 11/4 판부터 `o`(벤치 원점) 명령이 있으므로 이전에 올린 적이 있어도 다시 올린다. 업로드가 끝나면 시리얼 모니터를 닫는다.
2. **배선과 Vref**: `문서/배선_작업순서.md` 1~2단계(통전 검사, Vref 약 0.9 A)를 먼저 끝낸다. 12V를 켠 채 모터 선을 꽂거나 빼지 않는다.
3. **점검 스크립트**: `python hw_check.py`를 실행하고 질문에 y/n으로 답한다. 연결 → 드라이버 → 방향(m10) → 원점과 왕복 → 리밋 스위치 → 스피커 A·B 순서로 하나씩 움직이고, 결과를 `기록/hw_check_날짜.md`에 남긴다.
4. **이후**: step1·step3을 `--port` 없이 실행한다.

| 상태 | 원점 잡는 법 | 실행 예 |
|---|---|---|
| 조립 전 (모터만 책상 위, 리밋 스위치 없음) | 벤치 원점 `o`: 지금 위치를 0°로 믿음 | `python step1_turntable.py --demo --bench` |
| 조립 후 (리밋 스위치가 −70°에 달림) | 원점 찾기 `h` | `python step1_turntable.py --demo` |

벤치 모드에서는 모터 축에 테이프 깃발을 붙여 도는 방향과 각도를 눈으로 본다. 위에서 볼 때 반시계가 +이다.

## 모듈

- `turntable.py`: `Turntable` 클래스. `home()`, `bench_origin()`(리밋 스위치 없이 원점), `goto(각도)`, `nudge(각도)`, `enable(True/False)`, `status()`, `set_zero()`. 포트를 `"sim"`으로 주면 가짜 아두이노(`FakeArduino`)에 연결된다.
- `audio.py`: `tone(주파수, 초)`, `play(신호, side="A"|"B"|"AB", volume=0.3)`, `list_devices()`.

## 자주 생기는 문제

| 증상 | 해결 |
|---|---|
| 포트를 열 수 없음 | 아두이노 IDE의 시리얼 모니터를 닫는다. 포트는 한 프로그램만 쓸 수 있다. |
| 아두이노를 못 찾음 | USB 선(충전 전용 선이 아닌지), Windows는 CH340 드라이버, `--port COM3`처럼 직접 지정 |
| 소리가 반대 스피커 | 앰프 입력 또는 출력의 L·R 선을 바꾼다 |
| `PortAudio library not found` | Mac·Windows에서는 pip 설치에 포함된다. 다시 `pip install -r requirements.txt` |
| `o`에 "err 모르는 명령" | 아두이노에 옛 스케치가 올라가 있다. 최신 `turntable.ino`를 다시 업로드한다 |
| 이동 중 err로 멈춤 | 리밋 스위치가 눌렸다. `h`로 원점을 다시 찾는다 |
