"""모터판 구멍 본(실제 크기) PDF를 만든다.

    python motor_template.py      → 문서/모터판_구멍본.pdf

A4에 1:1로 그린다. 인쇄할 때 "실제 크기(100%)"로 인쇄하고 50mm 자로 확인한다.
NEMA17(17HS4401): 앞면 42.3mm 정사각형, 나사 구멍 M3 4개가 31mm 간격, 가운데 보스 Ø22.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, Rectangle

OUT = Path(__file__).resolve().parents[2] / "문서" / "모터판_구멍본.pdf"
FONT = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")

W, H = 210, 297          # A4 (mm)
CX, CY = 105, 165        # 본 중심의 종이 위 위치
HOLE = 31 / 2            # 모터 나사 구멍 중심까지 (mm)


def main():
    if FONT.exists():
        font_manager.fontManager.addfont(str(FONT))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(FONT)).get_name()
    fig = plt.figure(figsize=(W / 25.4, H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.axis("off")
    k = dict(color="black", lw=0.4)

    # 판 중심선과 맞출 십자선 (종이 끝까지)
    ax.plot([10, W - 10], [CY, CY], ls="--", **k)
    ax.plot([CX, CX], [60, H - 15], ls="--", **k)
    ax.text(W - 10, CY + 2, "판 중심선(가로)에 맞춤", ha="right", fontsize=7)
    ax.text(CX + 2, H - 17, "판 중심선(세로)에 맞춤", fontsize=7)
    ax.text(CX + 2, H - 22, "↑ 앞 (스피커 쪽)", fontsize=8)

    # 모터 앞면 윤곽과 보스, 가운데 구멍
    ax.add_patch(Rectangle((CX - 21.15, CY - 21.15), 42.3, 42.3, fill=False, ls=":", **k))
    ax.add_patch(Circle((CX, CY), 11, fill=False, ls=":", **k))
    ax.add_patch(Circle((CX, CY), 12.5, fill=False, color="black", lw=0.8))
    ax.text(CX, CY - 27, "가운데 Ø25 (스페이드 25mm)\n점선 사각형 = 모터 앞면 42.3, 점선 원 = 보스 Ø22",
            ha="center", va="top", fontsize=7)

    # 모터 나사 구멍 4개: 원 + 십자 (십자 가운데를 2mm 비트로 찍는다)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = CX + sx * HOLE, CY + sy * HOLE
            ax.add_patch(Circle((x, y), 2.0, fill=False, color="black", lw=0.8))
            ax.plot([x - 4, x + 4], [y, y], **k)
            ax.plot([x, x], [y - 4, y + 4], **k)
    ax.text(CX + HOLE + 5, CY + HOLE + 3, "모터 나사 Ø4 ×4\n(31mm 간격, M3×16)", fontsize=7)

    # 인쇄 크기 확인용 50mm 자
    y0 = 40
    ax.plot([30, 80], [y0, y0], color="black", lw=1)
    for i in range(0, 51, 10):
        ax.plot([30 + i, 30 + i], [y0, y0 + (3 if i % 50 else 5)], color="black", lw=1)
    ax.text(30, y0 - 6, "이 선이 정확히 50mm인지 자로 확인. 다르면 '실제 크기(100%)'로 다시 인쇄",
            fontsize=8)

    ax.text(15, H - 12, "모터판 구멍 본 (실제 크기, 1:1)", fontsize=13, weight="bold")
    steps = ("1) 모터판(250×250) 윗면에 대각선을 그어 가운데를 찾고, 가로·세로 중심선을 긋는다.\n"
             "2) 본의 점선 십자를 판 중심선에 맞추고 테이프로 붙인다. '앞' 화살표를 판의 앞쪽으로.\n"
             "3) 다섯 곳(가운데, 나사 4개)의 십자 가운데를 2mm 비트로 얕게 찍고 본을 뗀다.\n"
             "4) 나사 4개는 2mm로 관통한 뒤 4mm로 넓힌다. 가운데는 스페이드 25mm.\n"
             "5) 모터를 판 아래에서 대고 M3×16을 위에서 손으로 4개 다 걸고, 대각선 순서로 조인다.")
    ax.text(15, 25, steps, fontsize=7.5, va="top", linespacing=1.6)

    OUT.parent.mkdir(exist_ok=True)
    fig.savefig(OUT)
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
