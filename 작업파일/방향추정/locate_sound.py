"""마이크 녹음의 도착 시간차로 소리 방향을 구하고 SVG 그림에 점을 찍는다.

연습: python3 작업파일/방향추정/locate_sound.py --demo
추가 패키지 없이 Python 3.9 이상에서 실행한다. 자세한 설명은 같은 폴더의 README.md.
"""

import argparse
import csv
import itertools
import json
import math
import random
import struct
import sys
import wave
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOUND_SPEED = 343.0  # 음속, 단위 m/s. 실제 측정에서는 기온에 맞게 바꾼다.


def read_positions(path):
    """CSV의 첫 행은 녹음의 첫 번째 마이크 위치여야 한다. 단위는 m."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        rows = csv.DictReader(file)
        positions = [tuple(float(row[key]) for key in ("x_m", "y_m", "z_m"))
                     for row in rows]
    if len(positions) < 3 or not all(math.isfinite(v) for p in positions for v in p):
        raise ValueError("유한한 숫자로 적은 마이크 좌표가 최소 3개 필요해.")
    if any(abs(p[2] - positions[0][2]) > 1e-9 for p in positions):
        raise ValueError("첫 버전은 모든 마이크가 같은 z 평면에 있어야 해.")
    if len(set(positions)) != len(positions):
        raise ValueError("마이크 좌표가 중복돼 있어.")
    return positions


def read_recording(path, start_seconds=0.0):
    """WAV에서 최대 0.12초만 읽는다. PCM 16/24/32비트와 float32를 지원한다.

    Python 3.9의 wave는 일부 다채널 WAV를 못 읽어서 RIFF 구조를 직접 읽는다.
    WAV_FORMAT_EXTENSIBLE도 지원한다. MP3나 압축된 WAV는 지원하지 않는다.
    """
    with path.open("rb") as file:
        header = file.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise ValueError("일반 RIFF WAV 녹음 파일이 필요해.")
        fmt = None
        data_offset = None
        data_size = 0
        while True:
            chunk = file.read(8)
            if not chunk:
                break
            if len(chunk) != 8:
                raise ValueError("WAV의 구획 정보가 잘렸어.")
            name, size = struct.unpack("<4sI", chunk)
            offset = file.tell()
            if name == b"fmt ":
                fmt = file.read(min(size, 40))
            elif name == b"data":
                data_offset, data_size = offset, size
            if fmt is not None and data_offset is not None:
                break
            file.seek(offset + size + size % 2)
        if fmt is None or len(fmt) < 16 or data_offset is None:
            raise ValueError("WAV의 형식 정보 또는 녹음 데이터가 없어.")
        kind, count, rate, _, block, bits = struct.unpack("<HHIIHH", fmt[:16])
        if kind == 65534:  # 다채널 WAV에서 쓰는 확장 형식
            if len(fmt) < 40 or fmt[28:40] != bytes.fromhex("00001000800000aa00389b71"):
                raise ValueError("지원하지 않는 WAV 확장 형식이야.")
            kind = struct.unpack("<I", fmt[24:28])[0]
        if count < 3 or count > 64 or rate < 8000 or rate > 192000:
            raise ValueError("8~192 kHz로 동시에 녹음한 3~64채널 WAV가 필요해.")
        width = bits // 8
        if not ((kind == 1 and bits in (16, 24, 32)) or (kind == 3 and bits == 32)):
            raise ValueError("PCM 16/24/32비트 또는 float32 WAV로 저장해 줘.")
        if block != count * width or data_size % block:
            raise ValueError("WAV의 채널별 데이터 길이가 올바르지 않아.")
        first = int(start_seconds * rate)
        frames = min(int(0.12 * rate), data_size // block - first)
        if frames < 512:
            raise ValueError("선택한 시작 시점 뒤에 녹음이 너무 짧아. --start 값을 확인해 줘.")
        file.seek(data_offset + first * block)
        raw = file.read(frames * block)
    if len(raw) != frames * block:
        raise ValueError("WAV 녹음 데이터가 중간에 잘렸어.")
    if kind == 3:
        values = [v[0] for v in struct.iter_unpack("<f", raw)]
    elif bits in (16, 32):
        code = "<h" if bits == 16 else "<i"
        values = [v[0] / (2 ** (bits - 1)) for v in struct.iter_unpack(code, raw)]
    else:
        values = [int.from_bytes(raw[i:i + 3], "little", signed=True) / 8388608
                  for i in range(0, len(raw), 3)]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("녹음 안에 정상적인 숫자가 아닌 값이 있어.")
    return [values[channel::count] for channel in range(count)], rate


def make_demo(positions, path):
    """알고 있는 위치의 소리가 각 마이크에 도착하는 가상 녹음을 만든다.

    여기서만 정답을 사용한다. 방향을 찾는 estimate_direction에는 정답을 안 준다.
    """
    rate = 48000
    source = (0.55, 0.28, 1.5)  # 오른쪽 55cm, 위쪽 28cm, 앞쪽 1.5m
    rng = random.Random(42)
    tones = [(rng.uniform(300, 3200), rng.uniform(0, 2 * math.pi)) for _ in range(32)]
    channels = []
    for mic in positions:
        distance = math.dist(source, mic)
        channel = []
        for index in range(5760):
            time = index / rate - distance / SOUND_SPEED
            value = sum(math.sin(2 * math.pi * freq * time + phase) for freq, phase in tones)
            channel.append(value / 40 + rng.gauss(0, 0.002))
        channels.append(channel)
    with wave.open(str(path), "wb") as file:
        file.setparams((len(positions), 2, rate, 0, "NONE", "not compressed"))
        for frame in zip(*channels):
            file.writeframesraw(struct.pack("<" + "h" * len(frame),
                                           *(round(v * 32767) for v in frame)))
    return {"azimuth_deg": math.degrees(math.atan2(source[0], source[2])),
            "elevation_deg": math.degrees(math.atan2(source[1], math.hypot(source[0], source[2])))}


def find_delay(a, b, max_lag):
    """두 녹음을 조금씩 밀어 보며 가장 잘 겹치는 시간차를 찾는다.

    양의 lag: b에 소리가 더 늦게 도착했다는 뜻이다.
    """
    size = min(2048, len(a) - 2 * max_lag)
    if size < 128:
        raise ValueError("마이크 간격에 비해 분석할 녹음이 너무 짧아.")
    center = a[max_lag:max_lag + size]
    energy_a = sum(v * v for v in center)
    scores = []
    for lag in range(-max_lag, max_lag + 1):
        shifted = b[max_lag + lag:max_lag + lag + size]
        energy_b = sum(v * v for v in shifted)
        denominator = math.sqrt(energy_a * energy_b)
        scores.append(sum(x * y for x, y in zip(center, shifted)) / denominator
                      if denominator > 1e-20 else 0.0)
    peak = max(range(len(scores)), key=scores.__getitem__)
    if peak in (0, len(scores) - 1):
        raise ValueError("시간차가 탐색 경계에 걸렸어. 마이크 좌표와 녹음을 확인해 줘.")
    left, mid, right = scores[peak - 1:peak + 2]
    curvature = left - 2 * mid + right
    fraction = 0.5 * (left - right) / curvature if abs(curvature) > 1e-12 else 0.0
    return peak - max_lag + fraction, mid


def estimate_direction(channels, rate, positions, speed=SOUND_SPEED):
    """마이크 쌍의 시간차와 위치를 이용해 방향을 계산한다. 거리 추정은 하지 않는다."""
    if len(channels) != len(positions):
        raise ValueError("녹음 채널 수와 CSV 마이크 좌표 수가 달라.")
    clean = []
    for channel in channels:
        mean = sum(channel) / len(channel)
        values = [v - mean for v in channel]
        if math.sqrt(sum(v * v for v in values) / len(values)) < 1e-6:
            raise ValueError("무음이거나 값이 고정된 마이크가 있어. 녹음 시점을 확인해 줘.")
        clean.append(values)

    # 각 쌍에서 dx * ux + dy * uy = -음속 * 시간차. 모두에 가장 잘 맞는 ux, uy를 찾는다.
    xx = xy = yy = xb = yb = 0.0
    measurements = []
    for i, j in itertools.combinations(range(len(positions)), 2):
        dx = positions[j][0] - positions[i][0]
        dy = positions[j][1] - positions[i][1]
        max_lag = math.ceil(math.hypot(dx, dy) / speed * rate) + 2
        lag, similarity = find_delay(clean[i], clean[j], max_lag)
        if similarity < 0.4:
            continue
        difference = -speed * lag / rate
        xx += dx * dx
        xy += dx * dy
        yy += dy * dy
        xb += dx * difference
        yb += dy * difference
        measurements.append((dx, dy, difference))
    determinant = xx * yy - xy * xy
    if len(measurements) < 3 or xx * yy == 0 or determinant < 1e-8 * xx * yy:
        raise ValueError("두 방향을 계산할 정보가 부족해. 녹음·좌표·마이크 배치를 확인해 줘.")
    ux = (xb * yy - yb * xy) / determinant
    uy = (yb * xx - xb * xy) / determinant
    if ux * ux + uy * uy >= 1:
        raise ValueError("물리적으로 가능한 방향을 구하지 못했어. 채널 순서와 잡음을 확인해 줘.")
    # 앞쪽에 음원이 있다고 가정한다. 평면 배열의 시간차만으로 앞/뒤를 구분하지 않는다.
    uz = math.sqrt(1 - ux * ux - uy * uy)
    residual = math.sqrt(sum((dx * ux + dy * uy - value) ** 2
                             for dx, dy, value in measurements) / len(measurements))
    return {"azimuth_deg": math.degrees(math.atan2(ux, uz)),
            "elevation_deg": math.degrees(math.asin(uy)),
            "fit_error_samples": residual / speed * rate,
            "used_pairs": len(measurements)}


def save_plot(path, result, truth=None):
    """방향 좌표를 브라우저에서 열 수 있는 그림으로 저장한다."""
    def point(azimuth, elevation):
        return 400 + azimuth * 3.3, 320 - elevation * 2.5

    subtitle = "연습용 가상 녹음 · 실제 장비의 측정 결과가 아님" if truth else "실제 녹음 분석 · 한 음원이 앞쪽에 있다고 가정"
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="800" height="650" viewBox="0 0 800 650">',
             '<rect width="800" height="650" fill="#f5f7fa"/>',
             '<g font-family="sans-serif" fill="#172337">',
             '<text x="40" y="42" font-size="24">소리가 온 방향</text>',
             '<text x="40" y="73" font-size="15">' + subtitle + '</text>']
    for angle in range(-90, 91, 30):
        x, _ = point(angle, 0)
        _, y = point(0, angle)
        parts.extend([f'<path d="M{x} 95 V545 M103 {y} H697" stroke="#d3dbe5"/>',
                      f'<text x="{x}" y="568" text-anchor="middle">{angle}°</text>',
                      f'<text x="87" y="{y + 5}" text-anchor="end">{angle}°</text>'])
    parts.append('<path d="M400 95 V545 M103 320 H697" stroke="#66788d"/>')
    if truth:
        x, y = point(truth["azimuth_deg"], truth["elevation_deg"])
        parts.append(f'<circle cx="{x}" cy="{y}" r="13" fill="none" stroke="#147d64" stroke-width="3"/>')
    az, el = result["azimuth_deg"], result["elevation_deg"]
    x, y = point(az, el)
    parts.extend([f'<circle cx="{x}" cy="{y}" r="6" fill="#d33f40"/>',
                  '<text x="400" y="601" text-anchor="middle">← 왼쪽　　가로 각도（0° = 정면）　　오른쪽 →</text>',
                  '<text x="32" y="105">위쪽</text><text x="32" y="541">아래쪽</text>',
                  f'<text x="40" y="631">빨간 점: 계산 결과 ({az:.1f}°, {el:.1f}°)' +
                  ('　초록 원: 가상 녹음의 정답' if truth else '') + '</text>',
                  '</g></svg>'])
    path.write_text("\n".join(parts), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="마이크 녹음으로 소리 방향에 점 찍기")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--demo", action="store_true", help="가상 녹음으로 연습")
    inputs.add_argument("--wav", type=Path, help="동시에 녹음한 다채널 WAV")
    parser.add_argument("--positions", type=Path, help="녹음 채널 순서대로 적은 마이크 좌표 CSV")
    parser.add_argument("--start", type=float, default=0.0, help="분석 시작 시점(초)")
    parser.add_argument("--speed", type=float, default=SOUND_SPEED, help="음속(m/s)")
    args = parser.parse_args()
    if not math.isfinite(args.start) or args.start < 0 or not math.isfinite(args.speed) or args.speed <= 0:
        parser.error("시작 시점은 0 이상, 음속은 0보다 큰 유한한 숫자여야 해.")
    if not args.demo and args.positions is None:
        parser.error("실제 녹음에는 --positions로 실제 채널 순서의 좌표 CSV를 지정해야 해.")
    if args.demo and (args.positions is not None or args.start != 0 or args.speed != SOUND_SPEED):
        parser.error("--demo는 예시 좌표·기본 음속·시작 시점 0을 사용해.")
    try:
        positions = read_positions(args.positions or HERE / "mic_positions_example.csv")
        output = HERE / "결과" / ("연습" if args.demo else "실제녹음")
        output.mkdir(parents=True, exist_ok=True)
        truth = None
        recording = args.wav
        if args.demo:
            recording = output / "demo_16ch.wav"
            truth = make_demo(positions, recording)
        channels, rate = read_recording(recording, args.start)
        result = estimate_direction(channels, rate, positions, args.speed)
        result.update({"demo": args.demo, "source_file": str(recording.resolve()),
                       "start_seconds": args.start, "sound_speed_m_s": args.speed,
                       "distance_estimated": False, "front_hemisphere_assumed": True})
        if truth:
            result["demo_truth"] = truth
        save_plot(output / "direction.svg", result, truth)
        (output / "direction.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("【연습용 가상 녹음 결과】" if args.demo else "【실제 녹음 분석 결과】")
        print(f'가로 각도: {result["azimuth_deg"]:+.1f}° / 세로 각도: {result["elevation_deg"]:+.1f}°')
        print("＋는 오른쪽/위쪽, －는 왼쪽/아래쪽. 거리(m)를 측정한 결과는 아니야.")
        if result["fit_error_samples"] > 1:
            print("주의: 시간차가 한 방향으로 잘 맞지 않아. 채널 순서·반사·여러 음원을 확인해 줘.")
        print(f"결과 그림: {output / 'direction.svg'}")
    except (OSError, ValueError, KeyError, csv.Error, struct.error) as error:
        print(f"실행을 멈췄어: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
