"""녹음 WAV·마이크 좌표를 읽고, 계산 결과를 CSV 표로 저장한다."""

import csv
from pathlib import Path

import numpy as np
import soundfile as sf


def load_positions(path):
    """channel=0은 WAV의 첫 채널. CSV 행 순서에 상관없이 channel 순으로 정렬한다."""
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"channel", "x_m", "y_m", "z_m"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("좌표 CSV에 channel,x_m,y_m,z_m 열이 필요해.")
        rows = [(int(row["channel"]), float(row["x_m"]), float(row["y_m"]), float(row["z_m"]))
                for row in reader]
    rows.sort(key=lambda row: row[0])
    if not 3 <= len(rows) <= 64 or [row[0] for row in rows] != list(range(len(rows))):
        raise ValueError("channel은 0부터 시작해서 빠짐·중복 없이 3~64개여야 해.")
    positions = np.asarray([row[1:] for row in rows], dtype=float)
    if not np.all(np.isfinite(positions)):
        raise ValueError("마이크 좌표는 유한한 숫자여야 해.")
    return positions


def load_wav(path, start_seconds=0.0, duration_seconds=3.0):
    """WAV의 지정 구간을 (샘플, 채널) 모양으로 읽는다. 재생은 하지 않는다."""
    if not np.isfinite(start_seconds) or start_seconds < 0:
        raise ValueError("시작 시점은 0초 이상의 숫자여야 해.")
    if not np.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("분석 길이는 0초보다 큰 숫자여야 해.")
    with sf.SoundFile(str(path)) as file:
        if file.format not in ("WAV", "WAVEX", "RF64"):
            raise ValueError("이번 단계의 입력은 마이크를 동시에 녹음한 WAV 파일이야.")
        if not 3 <= file.channels <= 64:
            raise ValueError("3~64채널의 마이크 녹음이 필요해. 재생용 2채널 WAV는 쓸 수 없어.")
        start = int(start_seconds * file.samplerate)
        if start >= len(file):
            raise ValueError("분석 시작 시점이 녹음 끝을 넘어갔어.")
        file.seek(start)
        samples = file.read(frames=int(duration_seconds * file.samplerate), dtype="float64", always_2d=True)
        sample_rate = file.samplerate
    return samples, sample_rate


def save_result_tables(result, output, info):
    """그림의 근거가 되는 숫자를 엑셀·Numbers에서 열 수 있는 CSV로 저장한다."""
    output = Path(output)
    summary = {key: info[key] for key in (
        "input_mode", "hardware_accuracy_verified", "azimuth_deg", "elevation_deg",
        "channel_count", "sample_rate_hz", "duration_seconds", "temperature_c", "grid_step_deg",
    )}
    with (output / "summary.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(summary), lineterminator="\n")
        writer.writeheader()
        writer.writerow(summary)

    relative_db = result.relative_db
    zero_row = int(np.argmin(abs(result.elevations_deg)))
    columns = ["azimuth_deg", "elevation_deg", "power_uncalibrated", "relative_db"]
    with (output / "direction_curve.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(columns)
        for column, azimuth in enumerate(result.azimuths_deg):
            writer.writerow([azimuth, result.elevations_deg[zero_row],
                             result.power[zero_row, column], relative_db[zero_row, column]])

    with (output / "power_map.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(columns)
        for row, elevation in enumerate(result.elevations_deg):
            for column, azimuth in enumerate(result.azimuths_deg):
                writer.writerow([azimuth, elevation, result.power[row, column], relative_db[row, column]])
