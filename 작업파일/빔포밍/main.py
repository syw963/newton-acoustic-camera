"""이 파일부터 읽기: 1. 입력 준비 → 2. 방향 계산 → 3. 그림과 숫자 저장."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

try:
    import numpy as np
    import soundfile as sf
    from beamforming import beamform, sound_speed_from_temperature
    from data_io import load_positions, load_wav, save_result_tables
    from simulate import simulate_sources
except ModuleNotFoundError as error:
    sys.exit(f"필요한 패키지({error.name})가 없어. 프로젝트 폴더의 터미널에서 다음을 실행해 줘:\n"
             ".venv/bin/python -m pip install -r 작업파일/빔포밍/requirements.txt")


HERE = Path(__file__).resolve().parent


def parse_arguments():
    parser = argparse.ArgumentParser(description="마이크 녹음 → 지연-합 빔포밍 → 방향 각도와 소리 지도")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--demo", action="store_true", help="가상 16채널 녹음으로 실행")
    inputs.add_argument("--wav", type=Path, help="동시에 녹음한 다채널 WAV")
    parser.add_argument("--mic-positions", type=Path, help="실제 채널 순서를 확인한 좌표 CSV")
    parser.add_argument("--azimuth", type=float, default=20, help="가상 음원의 가로 각도, 기본 +20°")
    parser.add_argument("--elevation", type=float, default=10, help="가상 음원의 세로 각도, 기본 +10°")
    parser.add_argument("--two-sources", action="store_true", help="-30°와 +30°의 독립 가상 음원 두 개")
    parser.add_argument("--temperature", type=float, default=20, help="섭씨 기온, 기본 20°C")
    parser.add_argument("--fmin", type=float, default=500, help="분석 대역 하한 Hz")
    parser.add_argument("--fmax", type=float, default=4000, help="분석 대역 상한 Hz")
    parser.add_argument("--start", type=float, default=0, help="입력 WAV에서 분석 시작 시점(초)")
    parser.add_argument("--duration", type=float, default=3, help="분석 길이(초), 기본 3초")
    parser.add_argument("--step", type=int, choices=(1, 2, 5), default=2, help="방향 탐색 간격(도)")
    parser.add_argument("--block-size", type=int, default=1024, help="FFT 한 구간의 샘플 수")
    parser.add_argument("--output-dir", type=Path, help="결과를 저장할 새 폴더. 기존 폴더는 덮어쓰지 않음")
    args = parser.parse_args()
    if not args.demo and args.mic_positions is None:
        parser.error("입력 WAV에는 --mic-positions로 실제 채널 순서의 좌표 파일을 지정해야 해.")
    if args.demo and (args.mic_positions is not None or args.start != 0):
        parser.error("--demo는 예시 좌표와 시작 시점 0을 사용해.")
    if not args.demo and (args.two_sources or args.azimuth != 20 or args.elevation != 10):
        parser.error("--azimuth·--elevation·--two-sources는 가상 녹음에만 쓰는 옵션이야.")
    if args.two_sources and (args.azimuth != 20 or args.elevation != 10):
        parser.error("--two-sources는 (-30°, 0°), (+30°, 0°)를 사용해.")
    if not np.isfinite(args.duration) or args.duration <= 0 or not np.isfinite(args.start) or args.start < 0:
        parser.error("분석 길이는 양수, 시작 시점은 0 이상의 유한한 숫자여야 해.")
    return args


def main():
    args = parse_arguments()
    try:
        # 1. 입력 준비. 정답 각도는 가상 녹음 생성과 비교에만 쓰고 beamform에는 주지 않는다.
        sound_speed_from_temperature(args.temperature)
        positions_path = args.mic_positions or HERE / "mic_positions_example.csv"
        positions = load_positions(positions_path)
        if args.output_dir is not None:
            output = args.output_dir
            output.mkdir(parents=True, exist_ok=False)
        else:
            output_root = HERE / "결과"
            output_root.mkdir(exist_ok=True)
            output = Path(tempfile.mkdtemp(prefix="demo_" if args.demo else "wav_", dir=str(output_root)))
        truth = None
        recording_path = args.wav
        if args.demo:
            truth = [(-30.0, 0.0), (30.0, 0.0)] if args.two_sources else [(args.azimuth, args.elevation)]
            samples, rate = simulate_sources(positions, truth, seconds=args.duration, temperature_c=args.temperature)
            recording_path = output / "demo.wav"
            sf.write(str(recording_path), samples, rate, subtype="PCM_24")
            (output / "demo_truth.json").write_text(json.dumps({"directions_deg": truth,
                "model": "ideal_plane_wave", "hardware_measurement": False}, indent=2), encoding="utf-8")
        samples, rate = load_wav(recording_path, args.start, args.duration)

        # 2. 방향 계산. 나중에 실제 녹음을 연결할 때도 이 함수를 그대로 사용한다.
        print(f"{samples.shape[1]}채널, {len(samples) / rate:.2f}초의 녹음으로 방향을 계산하는 중…", flush=True)
        result = beamform(samples, rate, positions, fmin=args.fmin, fmax=args.fmax,
                          temperature_c=args.temperature, block_size=args.block_size,
                          azimuths_deg=np.arange(-90, 91, args.step),
                          elevations_deg=np.arange(-40, 41, args.step))

        # 3. 숫자와 그림 저장. 계산값과 정답 표시는 분리한다.
        azimuth, elevation = result.peak_direction
        info = {
            "algorithm": "frequency_domain_delay_and_sum",
            "input_mode": "simulation" if args.demo else "file",
            "hardware_accuracy_verified": False,
            # 공유할 결과에 개인 컴퓨터의 계정명·절대 경로를 넣지 않는다.
            "input_wav": recording_path.name,
            "mic_positions_file": positions_path.name,
            "path_format": "file_names_only",
            "mic_positions_m_in_channel_order": positions.tolist(),
            "processed_samples_sha256": hashlib.sha256(samples.tobytes()).hexdigest(),
            "sample_rate_hz": rate, "sample_count": len(samples), "channel_count": samples.shape[1],
            "start_seconds": int(args.start * rate) / rate, "duration_seconds": len(samples) / rate,
            "temperature_c": args.temperature, "sound_speed_m_s": result.sound_speed,
            "requested_band_hz": [args.fmin, args.fmax],
            "used_frequency_bins_hz": result.frequencies_hz.tolist(),
            "fft_block_size": result.block_size, "frame_count": result.frame_count,
            "window": "Hann", "overlap_fraction": 0.5, "csm_diagonal_kept": True,
            "grid_step_deg": args.step, "azimuth_range_deg": [-90, 90], "elevation_range_deg": [-40, 40],
            "azimuth_deg": azimuth, "elevation_deg": elevation,
            "front_hemisphere_assumed": True, "distance_estimated": False,
            "power_unit": "uncalibrated_mean_square", "relative_db_reference": "maximum_of_this_map",
            "software_versions": {"python": sys.version.split()[0], "numpy": np.__version__, "soundfile": sf.__version__},
        }
        np.savez_compressed(output / "power_map.npz", azimuths_deg=result.azimuths_deg,
                            elevations_deg=result.elevations_deg, power=result.power, relative_db=result.relative_db)
        (output / "result.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        save_result_tables(result, output, info)
        from plot_result import save_figure
        save_figure(result, output / "direction.png", demo=args.demo, truth=truth)
        print("【가상 녹음 분석 · 실제 측정 아님】" if args.demo else "【입력 WAV 분석 · 실물 정확도 검증은 별도】")
        print(f"가장 강한 방향: 가로 {azimuth:+.1f}°, 세로 {elevation:+.1f}°")
        print("+는 오른쪽/위쪽, -는 왼쪽/아래쪽. 거리는 추정하지 않아.")
        if truth:
            print(f"가상 녹음을 만들 때의 방향: {truth}")
        if abs(azimuth) == 90 or abs(elevation) == 40:
            print("최대점이 탐색 경계에 있어. 전체 지도와 탐색 범위를 확인해 줘.")
        if np.ptp(result.relative_db) < 1:
            print("방향별 차이가 1dB 미만으로 작아. 최대점만으로 방향을 확신하기 어려워.")
        print(f"결과 그림: {output / 'direction.png'}")
        print(f"결과 요약 표: {output / 'summary.csv'}")
        print(f"방향별 그래프 데이터: {output / 'direction_curve.csv'}")
        return 0
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print(f"실행을 멈췄어: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
