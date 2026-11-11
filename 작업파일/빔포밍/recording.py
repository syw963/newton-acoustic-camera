"""팀원의 SoundIO로 녹음하고, 분석 가능한 구간을 골라 빔포밍에 전달한다.

이 모듈을 불러오는 것만으로는 장치를 열거나 녹음하지 않는다.
"""

import importlib.util
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
FS = 48000
CHANNELS = 16


def team_audio_module():
    """팀원 파일을 복사하지 않고 현재 프로젝트의 원본을 불러온다."""
    path = HERE.parent / "sh" / "sound_io.py"
    spec = importlib.util.spec_from_file_location("newton_team_sound_io", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError) as error:
        raise RuntimeError(f"녹음 도구를 불러오지 못했어: {error}") from error
    if module.sd is None:
        raise RuntimeError("녹음 도구가 없어. .venv/bin/python -m pip install -r 작업파일/빔포밍/requirements.txt 를 실행해 줘.")
    return module


def show_devices():
    """장치 목록만 보여 준다. 녹음·재생은 시작하지 않는다."""
    module = team_audio_module()
    try:
        print(module.sd.query_devices())
    except module.sd.PortAudioError as error:
        raise RuntimeError(f"오디오 장치 목록을 읽지 못했어: {error}") from error
    print("입력은 UMA16v2, 출력은 앰프로 연결한 이어폰 단자를 선택해 줘.")


def assess_recording(recording, info):
    """녹음 경고·클리핑을 확인하고, 바닥 잡음보다 커진 가장 긴 구간을 찾는다.

    앞 0.2초는 재생 전에 녹음한 바닥 잡음이다. 20ms 구간별 RMS를 비교한다.
    이 검사는 방향 정확도나 음원 종류를 보증하는 검사가 아니다.
    """
    if (recording.ndim != 2 or recording.shape[1] != CHANNELS
            or recording.dtype != np.int16 or len(recording) < FS // 2):
        raise ValueError("최소 0.5초의 48kHz·16채널 int16 녹음이 필요해.")
    if info.get("fs") != FS or info.get("channels") != CHANNELS:
        raise ValueError("녹음 장치의 채널 수나 샘플링 주파수가 예상과 달라.")
    samples = recording.astype(float) / 32768
    peak = float(np.max(np.abs(samples)))
    result = {"ok": False, "sample_peak_full_scale": peak,
              "stream_warnings": info.get("warnings", ""),
              "criterion": "longest_20ms_RMS_run_above_3x_first_0.2s_noise_floor"}
    if info.get("warnings"):
        result["reason"] = "녹음 중 스트림 경고가 발생했어. 샘플 누락 가능성이 있어 다시 녹음해야 해."
        return result
    if peak >= 0.99:
        result["reason"] = "녹음이 최대 크기에 가까워 찌그러졌을 수 있어. 앰프 볼륨을 낮추고 다시 녹음해 줘."
        return result

    frame_size = FS // 50  # 20ms
    frame_count = len(samples) // frame_size
    blocks = samples[:frame_count * frame_size].reshape(frame_count, frame_size, CHANNELS)
    rms = np.sqrt(np.mean(blocks ** 2, axis=(1, 2)))
    baseline = float(np.median(rms[:10]))  # 앞 0.2초
    threshold = max(baseline * 3, 1e-5)
    active = rms > threshold
    active[:10] = False
    best_start = best_stop = run_start = 0
    for index, is_active in enumerate(active):
        if not is_active:
            run_start = index + 1
        elif index + 1 - run_start > best_stop - best_start:
            best_start, best_stop = run_start, index + 1
    result.update({"baseline_rms": baseline, "active_threshold_rms": threshold})
    if best_stop - best_start < 10:  # 0.2초 이상 유지된 소리
        result["reason"] = "시험 소리가 바닥 잡음보다 충분히 크게 잡히지 않았어. 출력 장치·스피커·주변 소음을 확인해 줘."
        return result
    result.update({"ok": True, "start_seconds": best_start * frame_size / FS,
                   "duration_seconds": (best_stop - best_start) * frame_size / FS})
    return result


def capture_recording(output, *, sound="exp3_white", speaker="A", volume=0.3,
                      mic=None, out_device=None):
    """실제 녹음 → 원본 보존 → 상태 확인. 원본 팀 모듈은 실행 시 불러온다."""
    if not np.isfinite(volume) or not 0 < volume <= 1:
        raise ValueError("볼륨은 0보다 크고 1 이하여야 해.")
    module = team_audio_module()
    # 파일·볼륨 오류는 장치를 열거나 소리를 내기 전에 확인한다.
    module.load_signal(sound)
    try:
        sound_io = module.SoundIO(mic=mic, speaker=out_device)
        if sound_io.mic_channels != CHANNELS:
            raise ValueError("UMA-16의 16채널 입력이 필요해. 노트북 내장 마이크로 대체하지 않아.")
        print(f"입력 마이크: {sound_io._name(sound_io.mic)}", flush=True)
        print(f"출력 스피커: {sound_io._name(sound_io.speaker)}", flush=True)
        print(f"스피커 {speaker}에서 {sound} 재생과 16채널 녹음을 시작해. 잠시 조용히 해 줘.", flush=True)
        recording, info = sound_io.play_and_record(sound, speaker, volume=volume, pre_roll=0.3, post_roll=0.5)
    except module.sd.PortAudioError as error:
        raise RuntimeError(f"재생·녹음을 시작하거나 마치지 못했어. 장치 연결·마이크 권한·출력 선택을 확인해 줘: {error}") from error
    output = Path(output)
    path = sound_io.save(recording, output / "recording.wav")
    print(f"원본 녹음 저장: {path}", flush=True)
    try:
        quality = assess_recording(recording, info)
    except ValueError as error:
        quality = {"ok": False, "reason": str(error)}
    metadata = {"capture": info, "quality": quality, "pre_roll_seconds": 0.3, "post_roll_seconds": 0.5}
    (output / "recording_info.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    if not quality["ok"]:
        raise ValueError(f"{quality['reason']} 원본은 {path}에 보존했어. 방향 계산은 하지 않았어.")
    print(f"소리가 잡힌 구간: {quality['start_seconds']:.2f}초부터 {quality['duration_seconds']:.2f}초", flush=True)
    return Path(path), metadata
