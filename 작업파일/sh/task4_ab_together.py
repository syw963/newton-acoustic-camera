"""연습 과제 4: 스피커 A에는 1 kHz, 스피커 B에는 2 kHz를 동시에 낸다.

(문서/소프트웨어_첫걸음.html 5장. audio.py는 작업파일/파이썬/에서 복사해 온 것)

실행:  python task4_ab_together.py
"""
import numpy as np

import audio

# ---- 여기 숫자를 바꿔 보세요 ----
FREQ_A = 1000    # 스피커 A(왼쪽 채널)로 낼 주파수, Hz
FREQ_B = 2000    # 스피커 B(오른쪽 채널)로 낼 주파수, Hz
SECONDS = 2      # 소리 길이, 초
# ---------------------------------

# 1. 소리 두 개를 만든다.
#    소리는 "1초에 48000번 잰 공기 압력 값"을 줄줄이 늘어놓은 숫자 목록이다.
#    2초면 숫자 96000개짜리 목록이 된다.
a = audio.tone(FREQ_A, SECONDS)
b = audio.tone(FREQ_B, SECONDS)

# 2. 두 목록을 나란히 붙여 표 하나로 만든다 (힌트의 numpy.column_stack).
#    왼쪽 칸 = A의 숫자, 오른쪽 칸 = B의 숫자.
#    노트북은 왼쪽 칸을 이어폰 왼쪽(스피커 A)으로, 오른쪽 칸을 오른쪽(스피커 B)으로 보낸다.
stereo = np.column_stack([a, b])

# 3. 모양을 확인한다. (행 수, 열 수)로 나온다.
print("A 소리:", a.shape, "  B 소리:", b.shape, "  붙인 표:", stereo.shape)
print("표의 맨 앞 5줄 (왼쪽 칸 = A, 오른쪽 칸 = B):")
print(np.round(stereo[:5], 4))

# 4. 재생한다. 이미 두 칸짜리 표라서 audio.play가 그대로 낸다. 볼륨 기본값은 0.3.
print(f"재생: A {FREQ_A} Hz + B {FREQ_B} Hz, {SECONDS}초 동시에")
audio.play(stereo)
print("끝")
