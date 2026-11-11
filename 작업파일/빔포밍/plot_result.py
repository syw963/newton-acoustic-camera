"""계산된 각도별 세기를 PNG 그림으로 저장한다. 계산 자체는 하지 않는다."""

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")  # 창을 띄우거나 장비를 연결하지 않고 그림 파일만 만든다.
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np


def save_figure(result, path, *, demo=False, truth=None):
    font_path = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
    korean = font_path.exists()
    if korean:
        font_manager.fontManager.addfont(str(font_path))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font_path)).get_name()
    plt.rcParams["axes.unicode_minus"] = False
    azimuth, elevation = result.peak_direction
    figure, (map_axis, curve_axis) = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    title = "가상 녹음 분석 · 실제 측정 결과 아님" if demo else "입력 WAV 분석 · 실제 정확도 검증은 별도"
    if not korean:
        title = "Simulated recording - not a hardware measurement" if demo else "Input WAV analysis - hardware accuracy unverified"
    figure.suptitle(title, fontsize=16)
    image = map_axis.pcolormesh(result.azimuths_deg, result.elevations_deg, result.relative_db,
                               shading="auto", cmap="magma", vmin=-15, vmax=0)
    map_axis.plot(azimuth, elevation, "w*", markersize=13, markeredgecolor="black",
                  label="계산 최대점" if korean else "Estimated maximum")
    for i, (az, el) in enumerate(truth or []):
        map_axis.plot(az, el, "o", markerfacecolor="none", markeredgecolor="#40e0ac", markersize=16,
                      markeredgewidth=2, label=("가상 정답" if korean else "Simulation truth") if i == 0 else None)
    map_axis.set(xlabel="가로 각도 (°)" if korean else "Azimuth (degrees)",
                 ylabel="세로 각도 (°)" if korean else "Elevation (degrees)",
                 title="방향별 소리 세기" if korean else "Directional power map")
    figure.colorbar(image, ax=map_axis, label="상대 세기 (dB)" if korean else "Relative power (dB)")
    map_axis.legend(loc="lower right", fontsize=8)
    # 실험 1·2의 기본 가로 그래프를 위해 항상 세로 0°에서 자른다.
    zero_row = int(np.argmin(abs(result.elevations_deg)))
    curve_axis.plot(result.azimuths_deg, result.relative_db[zero_row], color="#3468b2", linewidth=2)
    curve_axis.axhline(-3, color="#7b8490", linestyle="--", label="-3 dB")
    for az, _ in truth or []:
        curve_axis.axvline(az, color="#147d64", linestyle=":")
    curve_axis.set(xlim=(-90, 90), ylim=(-25, 1),
                   xlabel="가로 각도 (°)" if korean else "Azimuth (degrees)",
                   ylabel="지도 최대값 기준 (dB)" if korean else "Relative to map maximum (dB)",
                   title="세로 0°에서 본 가로 그래프" if korean else "Horizontal slice at elevation 0 degrees")
    curve_axis.grid(alpha=0.25)
    curve_axis.legend()
    figure.savefig(str(path), dpi=160)
    plt.close(figure)
