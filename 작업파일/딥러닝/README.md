# 실험 3: 딥러닝 방향 추정

16채널 녹음에서 GCC-PHAT 특징을 만들고, 작은 합성곱 신경망이 소리 방향(연속 각도)을 맞히게 학습한다.
같은 시험 녹음으로 지연-합 빔포밍(DAS), SRP-PHAT, MUSIC과 평균 오차·최대 오차를 비교한다.

## 흐름

```
collect.py ──▶ 수집/날짜_장소/*.wav + labels.csv      (회전판 무작위 각도, 정답 = 모터 각도)
make_dataset.py ──▶ 데이터/*.npz                       (GCC-PHAT 120쌍 × 65칸, 작음)
train.py ──▶ 결과/이름/model.pt, log.csv, loss.png     (노트북 또는 RunPod)
evaluate.py ──▶ 결과/이름/eval_*/summary.csv, error.png (4가지 방법 비교)
```

| 파일 | 하는 일 |
|---|---|
| `data.py` | 가짜 녹음(반사·감도 차이·잡음 포함)과 수집 폴더 읽기 |
| `gcc.py` | GCC-PHAT 특징, SRP-PHAT |
| `model.py` | 신경망 (입력 120×65 → 각도 1개) |
| `collect.py` | 회전판 + 스피커 + UMA-16 자동 수집 |
| `make_dataset.py` | 녹음 → npz |
| `train.py` | 학습 (cuda / Mac mps / cpu 자동) |
| `evaluate.py` | DAS·SRP-PHAT·MUSIC·DNN 비교 |

마이크 좌표와 빔포밍은 `../파이썬/beamform.py`, 재생·녹음은 `../sh/sound_io.py`, 회전판은 `../파이썬/turntable.py`를 불러 쓴다.
각도는 배열 뒤에서 볼 때 오른쪽이 +이다(beamform.py와 같음, D3에서 확정).

## 1. 지금 바로 (장치 없이)

```bash
pip install -r requirements.txt
python make_dataset.py --sim 4000 --out 데이터/sim_train.npz      # 약 1.5분
python train.py --train 데이터/sim_train.npz --out 결과/sim1 --epochs 30   # Mac에서 약 30초
python evaluate.py --model 결과/sim1/model.pt --sim 300 --seed 99
python collect.py --n 5 --place 연습 --sim                        # 수집 흐름 점검
```

2026-11-13 결과 (가짜 녹음 시험 300개, ±60°):

| 방법 | 평균 오차 | 최대 오차 |
|---|---|---|
| DAS | 0.55° | 4.6° |
| SRP-PHAT | 0.25° | 5.0° |
| MUSIC | 1.13° | 7.9° |
| DNN | 0.50° | 2.4° |

같은 모델을 11/11 실제 녹음에 돌리면 빔포밍과 10~25° 차이가 난다. 가짜 녹음은 실제 방(스피커 특성, 반사, 근접 거리)을 다 흉내 내지 못한다.
그래서 **실제 수집 데이터로 학습해야 한다.** 가짜 녹음 모델은 출발점(사전 학습, `--init`)으로만 쓴다.

## 2. 회전판이 완성되면: 수집

1. 스피커 A를 배열 정면 1 m, 배열 중심 높이에 둔다. 회전판의 연필 0° 표시를 맞춘다.
2. `python collect.py --n 300 --place 과학실 --distance 1.0 --temp 22`
   - 한 번에 약 3초 → 300개에 약 15~20분.
   - 시작할 때와 50회마다 0°로 돌아가 빔포밍으로 정면(±3°)을 확인한다. 어긋나면 멈춘다.
   - 멈추거나 Ctrl+C로 끊어도 `--out 수집/폴더`로 다시 실행하면 이어서 모은다.
3. **시험용 세션은 따로 모은다.** 다른 날, 다른 장소, 다른 거리 중 하나 이상을 바꾼다.
   같은 세션을 무작위로 나눠 시험하면 점수가 부풀려진다(data leakage).

권장 묶음 (예시):

| 용도 | 세션 |
|---|---|
| 학습 | 과학실 1 m (2회, 다른 날), 과학실 1.5 m |
| 검증 | 과학실 0.7 m |
| 시험 | 도서관(또는 복도) 1 m — 학습에 한 번도 안 쓴 곳 |

```bash
python make_dataset.py --session 수집/20261120_과학실 수집/20261121_과학실 수집/20261121_과학실15 --out 데이터/real_train.npz
python make_dataset.py --session 수집/20261122_과학실07 --out 데이터/real_val.npz
python train.py --train 데이터/real_train.npz --val 데이터/real_val.npz --init 결과/sim1/model.pt --out 결과/real1
python evaluate.py --model 결과/real1/model.pt --session 수집/20261127_도서관
```

## 3. RunPod에서 학습하기

모델이 작아서 지금 크기(수천 개)는 Mac으로도 충분하다. 데이터가 수만 개로 늘거나 여러 설정을 한꺼번에 돌릴 때 RunPod를 쓴다.

1. runpod.io → Pods → Deploy. 템플릿 **RunPod PyTorch**, GPU는 가장 싼 것(RTX A4000/3090급)이면 된다.
2. Pod의 **Connect → Jupyter Lab** 또는 Web Terminal을 연다.
3. 코드 받기
   ```bash
   cd /workspace
   git clone https://github.com/syw963/newton-acoustic-camera.git
   cd newton-acoustic-camera/작업파일/딥러닝
   pip install numpy matplotlib soundfile
   ```
4. 데이터 올리기: Jupyter Lab 왼쪽 파일 창에 `데이터/*.npz`를 끌어다 놓는다(wav는 올리지 않는다).
   가짜 녹음만 쓸 거면 Pod에서 `make_dataset.py --sim`을 바로 돌려도 된다.
5. `python train.py --train 데이터/real_train.npz --val 데이터/real_val.npz --out 결과/real1 --epochs 60`
6. `결과/real1/` 폴더(model.pt, log.csv, loss.png)를 내려받는다. 평가는 wav가 있는 Mac에서 `evaluate.py`로 한다.
7. **다 쓰면 Pod를 Stop이 아니라 Terminate** 해야 요금이 멈춘다(Stop은 저장 공간 요금이 계속 나간다).

## 해석할 때 주의

- 학습 곡선(loss.png)에서 학습 오차만 내려가고 검증 오차가 올라가면 외워 버린 것(과적합)이다. 데이터를 늘리거나 `--epochs`를 줄인다.
- 정답(모터 각도)에도 오차가 있다. 0° 표시 맞춤, 스텝 반올림(0.1125°), 스피커 위치. 평균 오차가 1° 아래로 내려가면 정답 오차와 구분하기 어렵다.
- DNN은 학습 범위(±60°) 밖은 맞히지 못한다. 평가도 ±60° 안에서만 한다.
