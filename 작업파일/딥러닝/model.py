"""방향 추정 신경망. 입력 GCC-PHAT (120쌍, 65칸) → 출력 각도 하나(연속값, 회귀).

120쌍을 채널로 보고 시간차 축으로 1차원 합성곱을 한다. 매개변수 약 30만 개로 작아서
노트북 CPU로도 몇 분이면 학습된다. 데이터가 많아지면 RunPod GPU에서 같은 코드를 돌린다.
"""

import torch
from torch import nn

SCALE = 90.0   # 각도를 ±1 근처로 줄여서 학습한다


class DoaNet(nn.Module):
    def __init__(self, pairs=120, width=128, dropout=0.2):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(pairs, width, 5, padding=2), nn.BatchNorm1d(width), nn.ReLU(),
            nn.Conv1d(width, width, 5, padding=2), nn.BatchNorm1d(width), nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(width, width, 3, padding=1), nn.BatchNorm1d(width), nn.ReLU(),
            nn.AdaptiveAvgPool1d(4),
        )
        self.head = nn.Sequential(
            nn.Flatten(), nn.Dropout(dropout),
            nn.Linear(width * 4, 128), nn.ReLU(),
            nn.Linear(128, 1),
        )

    def forward(self, x):            # x: (배치, 120, 65)
        return self.head(self.conv(x)).squeeze(1) * SCALE   # 각도(°)


def load(path, device="cpu"):
    ck = torch.load(path, map_location=device)
    m = DoaNet(**ck["config"]).to(device)
    m.load_state_dict(ck["state"])
    m.eval()
    return m, ck
