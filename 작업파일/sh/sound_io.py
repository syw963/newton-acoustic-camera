"""소리 재생 + UMA-16 동시 녹음 (Windows, Mac 공용)

연결: 노트북 이어폰 단자 → 앰프(PAM8403) → 왼쪽 채널 = 스피커 A, 오른쪽 채널 = 스피커 B
녹음: UMA-16 v2 (USB, 16채널, 48 kHz)
소리 파일: ../신호/signals/*.wav (make_signals.py로 만든 것)

명령 (이 폴더에서 실행)
  python sound_io.py devices                                 소리 장치 목록과 고른 장치
  python sound_io.py play exp1_tone_1k --speaker A           재생만
  python sound_io.py play exp1_tone_1k exp1_tone_2k --speaker B --gap 1
  python sound_io.py play exp2_band_4k --speaker A --repeat 0   (0 = Ctrl+C를 누를 때까지 반복)
  python sound_io.py rec exp3_white --speaker A              재생하면서 16채널 녹음 → 기록/
  python sound_io.py rec exp3_white --speaker A --mic default   UMA-16 없이 노트북 마이크로 시험
  python sound_io.py selftest                                노트북 스피커·마이크로 동시 시작 확인

--speaker: A = 왼쪽만, B = 오른쪽만, AB = 파일 그대로 (실험 2)
  A 전용 파일(실험 1·3)을 B로 고르면 같은 소리가 오른쪽(B)으로 나간다.
--volume: 0~1, 기본 0.3 (팀장 audio.py와 같은 약속. 처음엔 낮게, 실험 중에는 바꾸지 않는다)

필요한 패키지는 팀장의 작업파일/파이썬/requirements.txt와 같다 (numpy, sounddevice, soundfile).

다른 프로그램에서 쓰기
  from sound_io import SoundIO
  sio = SoundIO()                                  # 장치를 한 번 찾아 둔다
  rec, info = sio.play_and_record("exp3_white", "A", volume=0.3)
  sio.save(rec, "data/train_A/A_00001.wav")
  sio.play("exp2_band_4k", "B")                    # 녹음 없이 재생만
"""
import argparse
import csv
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

try:
    import sounddevice as sd
except ImportError:  # 장치 없이 하는 시험(test_sound_io.py)은 sounddevice 없이도 돈다
    sd = None

HERE = Path(__file__).resolve().parent
SIGNAL_DIR = HERE.parent / "신호" / "signals"
REC_DIR = HERE / "기록"

FS = 48000            # 소리 파일과 녹음의 표본화 주파수 (Hz)
VOLUME = 0.3          # 기본 볼륨 (0~1)
MIC_CHANNELS = 16     # UMA-16 채널 수
MIC_HINTS = ("uma16", "minidsp")   # UMA-16 장치 이름에 들어 있을 글자 (띄어쓰기·하이픈 무시)
PRE_ROLL = 0.3        # 녹음을 소리보다 먼저 시작하는 시간 (s)
POST_ROLL = 0.5       # 소리가 끝난 뒤 더 녹음하는 시간 (s). 1.5 m 전파는 약 4.4 ms, 나머지는 잔향·지연 여유


# ---------------------------------------------------------------- 소리 파일

def load_signal(name):
    """소리 파일을 (표본 수, 2) float32 배열로 읽는다. name은 'exp3_white', 'exp3_white.wav', 경로 모두 된다."""
    path = Path(name)
    if not path.exists():
        path = SIGNAL_DIR / (name if name.endswith(".wav") else name + ".wav")
    if not path.exists():
        have = ", ".join(sorted(p.stem for p in SIGNAL_DIR.glob("*.wav")))
        raise FileNotFoundError(f"소리 파일 '{name}'이 없다. 있는 파일: {have}")
    x, fs = sf.read(str(path), dtype="float32")
    if fs != FS:
        raise ValueError(f"{path.name}의 표본화 주파수가 {fs} Hz이다. {FS} Hz여야 한다.")
    if x.ndim == 1:
        x = np.stack([x, np.zeros_like(x)], axis=1)   # 모노 파일은 왼쪽(A)에 둔다
    return x[:, :2]


def route(stereo, speaker):
    """speaker에 맞게 채널을 고른다. A = 왼쪽만, B = 오른쪽만, AB = 그대로."""
    speaker = speaker.upper()
    if speaker == "AB":
        return stereo.copy()
    if speaker not in ("A", "B"):
        raise ValueError("speaker는 A, B, AB 중 하나여야 한다.")
    left, right = stereo[:, 0], stereo[:, 1]
    src = left if speaker == "A" else right
    if not np.any(src):                  # 그 채널이 비어 있으면(한쪽 전용 파일) 다른 채널의 소리를 쓴다
        src = right if speaker == "A" else left
    out = np.zeros_like(stereo)
    out[:, 0 if speaker == "A" else 1] = src
    return out


# ---------------------------------------------------------------- 장치 고르기

def _norm(s):
    return s.lower().replace(" ", "").replace("-", "").replace("_", "")


def pick_device(devices, hostapis, hint, kind, default_idx):
    """장치 번호를 고른다.

    hint: None 또는 'default' = 기본 장치, 숫자 = 그 번호, 글자 또는 글자 묶음 = 이름에 그 글자가 든 장치
    Windows에서는 같은 장치가 MME·DirectSound·WASAPI·WDM-KS로 여러 번 보이므로 WASAPI를 먼저 고른다.
    (MME는 채널 수가 제한될 수 있다.)
    """
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    wasapi = next((i for i, h in enumerate(hostapis) if "WASAPI" in h["name"]), None)

    if hint is None or hint == "default":
        if wasapi is not None:
            idx = hostapis[wasapi]["default_input_device" if kind == "input" else "default_output_device"]
            if idx is not None and idx >= 0:
                return idx
        return default_idx

    if isinstance(hint, int) or str(hint).isdigit():
        return int(hint)

    hints = (hint,) if isinstance(hint, str) else tuple(hint)
    found = [i for i, d in enumerate(devices)
             if d[key] > 0 and any(_norm(h) in _norm(d["name"]) for h in hints)]
    if not found:
        raise LookupError(f"이름에 {' 또는 '.join(hints)}이(가) 들어간 {'입력' if kind == 'input' else '출력'} 장치가 없다. "
                          "'python sound_io.py devices'로 목록을 확인한다.")
    # WASAPI 장치를 먼저, 그다음 채널이 많은 장치를 고른다
    found.sort(key=lambda i: (devices[i]["hostapi"] != wasapi, -devices[i][key]))
    return found[0]


# ---------------------------------------------------------------- 재생·녹음

class SoundIO:
    def __init__(self, mic=None, speaker=None, need_mic=True):
        """mic: None = UMA-16을 찾음, 'default' = 노트북 기본 마이크(시험용), 그 밖 = 장치 이름 일부나 번호
        speaker: None 또는 'default' = 기본 출력(이어폰 단자), 그 밖 = 장치 이름 일부나 번호"""
        if sd is None:
            raise ImportError("sounddevice가 설치되어 있지 않다. 'python -m pip install sounddevice'를 실행한다.")
        devices, hostapis = sd.query_devices(), sd.query_hostapis()
        self.speaker = pick_device(devices, hostapis, speaker, "output", sd.default.device[1])
        self.mic = None
        self.mic_channels = 0
        if need_mic:
            self.mic = pick_device(devices, hostapis, MIC_HINTS if mic is None else mic, "input", sd.default.device[0])
            self.mic_channels = min(MIC_CHANNELS, sd.query_devices(self.mic)["max_input_channels"])
            if mic is None and self.mic_channels < MIC_CHANNELS:
                raise RuntimeError(f"UMA-16 장치가 {self.mic_channels}채널만 보인다. 16채널이어야 한다. 사용법.md의 문제 해결을 본다.")

    def _name(self, idx):
        d = sd.query_devices(idx)
        return f"{d['name']} ({sd.query_hostapis(d['hostapi'])['name']})"

    def _extra(self, idx):
        """WASAPI 장치면 Windows 소리 설정과 표본화 주파수가 달라도 변환해 주게 한다."""
        if "WASAPI" in sd.query_hostapis(sd.query_devices(idx)["hostapi"])["name"]:
            return sd.WasapiSettings(auto_convert=True)
        return None

    def _play_blocking(self, data):
        """data를 끝까지 재생한다. 첫 표본이 스피커로 나간 시각(스트림 시각, s)을 돌려준다."""
        pos = [0]
        t = {}
        done = threading.Event()

        def callback(outdata, frames, tm, status):
            if pos[0] == 0:
                t["dac"] = tm.outputBufferDacTime
            chunk = data[pos[0]:pos[0] + frames]
            outdata[:len(chunk)] = chunk
            outdata[len(chunk):] = 0
            pos[0] += frames
            if pos[0] >= len(data):
                raise sd.CallbackStop

        with sd.OutputStream(device=self.speaker, channels=2, samplerate=FS, dtype="float32",
                             callback=callback, finished_callback=done.set,
                             extra_settings=self._extra(self.speaker)):
            if not done.wait(len(data) / FS + 5):
                raise RuntimeError("재생이 끝나지 않는다. 출력 장치를 확인한다.")
        return t.get("dac", 0.0)

    @staticmethod
    def _prepare(sound, speaker, volume):
        if not 0 < volume <= 1:
            raise ValueError("volume은 0보다 크고 1 이하여야 한다.")
        return np.clip(route(load_signal(sound), speaker) * volume, -1, 1).astype(np.float32)

    def play(self, sound, speaker="A", volume=VOLUME):
        """녹음 없이 재생만 한다."""
        self._play_blocking(self._prepare(sound, speaker, volume))

    def play_and_record(self, sound, speaker="A", volume=VOLUME, pre_roll=PRE_ROLL, post_roll=POST_ROLL):
        """녹음을 먼저 시작하고 pre_roll 뒤에 소리를 낸다. 소리가 끝나고 post_roll 뒤에 녹음을 멈춘다.

        돌려주는 값: (녹음 int16 배열 (표본 수, 채널 수), 기록 dict)
        """
        if self.mic is None:
            raise RuntimeError("SoundIO(need_mic=False)로 만들면 녹음할 수 없다.")
        data = self._prepare(sound, speaker, volume)
        blocks, t_in, warnings = [], {}, []
        started = threading.Event()

        def callback(indata, frames, tm, status):
            if status:
                warnings.append(str(status))
            if not blocks:
                t_in["adc"] = tm.inputBufferAdcTime
            blocks.append(indata.copy())
            started.set()

        with sd.InputStream(device=self.mic, channels=self.mic_channels, samplerate=FS, dtype="int16",
                            callback=callback, extra_settings=self._extra(self.mic)):
            if not started.wait(3):
                raise RuntimeError("마이크에서 소리가 들어오지 않는다. 장치 연결과 마이크 권한을 확인한다.")
            time.sleep(pre_roll)
            t_out = self._play_blocking(data)
            time.sleep(post_roll)

        rec = np.concatenate(blocks)
        peak = float(np.max(np.abs(rec.astype(np.int32)))) / 32767
        offset = None
        if t_out and t_in.get("adc"):
            offset = round(t_out - t_in["adc"], 4)
        info = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "sound": Path(sound).stem,
            "speaker": speaker.upper(),
            "volume": volume,
            "fs": FS,
            "channels": rec.shape[1],
            "rec_s": round(len(rec) / FS, 3),
            "sound_s": round(len(data) / FS, 3),
            "play_offset_s": offset,        # 녹음 첫 표본 → 소리 첫 표본 (추정값, 두 장치의 시계 차이 포함)
            "peak": round(peak, 4),         # 1이면 찌그러짐
            "warnings": "; ".join(sorted(set(warnings))),
            "mic": self._name(self.mic),
            "out": self._name(self.speaker),
        }
        return rec, info

    @staticmethod
    def save(rec, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(path), rec, FS, subtype="PCM_16")
        return path


# ---------------------------------------------------------------- 명령

def find_onset(x, pre_roll):
    """녹음 x(한 채널, float)에서 소리가 시작된 표본 번호. 못 찾으면 None."""
    noise = x[: int(FS * pre_roll * 0.8)]
    noise_rms = float(np.sqrt(np.mean(noise ** 2))) if len(noise) else 0.0
    env = np.abs(x)
    thr = max(5 * noise_rms, 0.2 * float(env.max()))
    if env.max() < 5 * noise_rms or env.max() == 0:
        return None
    return int(np.argmax(env > thr))


def cmd_devices(args):
    print(sd.query_devices())
    print()
    sio = SoundIO(speaker=args.out, need_mic=False)
    print(f"출력(스피커): {sio._name(sio.speaker)}")
    try:
        sio = SoundIO(mic=args.mic, speaker=args.out)
        print(f"입력(마이크): {sio._name(sio.mic)}, {sio.mic_channels}채널")
    except (LookupError, RuntimeError) as e:
        print(f"입력(마이크): 찾지 못함 - {e}")


def cmd_play(args):
    sio = SoundIO(speaker=args.out, need_mic=False)
    print(f"출력: {sio._name(sio.speaker)}")
    n = 0
    try:
        while args.repeat == 0 or n < args.repeat:
            for s in args.sounds:
                print(f"재생: {s} → 스피커 {args.speaker.upper()} (볼륨 {args.volume})")
                sio.play(s, args.speaker, args.volume)
                time.sleep(args.gap)
            n += 1
    except KeyboardInterrupt:
        print("\n멈춤")


def cmd_rec(args):
    sio = SoundIO(mic=args.mic, speaker=args.out)
    print(f"마이크: {sio._name(sio.mic)}, {sio.mic_channels}채널 / 출력: {sio._name(sio.speaker)}")
    out_dir = Path(args.out_dir)
    for s in args.sounds:
        rec, info = sio.play_and_record(s, args.speaker, args.volume)
        name = f"{datetime.now():%Y%m%d_%H%M%S}_{info['sound']}_{info['speaker']}.wav"
        path = sio.save(rec, out_dir / name)
        info["file"] = path.name
        log = out_dir / "rec_log.csv"
        new = not log.exists()
        with open(log, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(info))
            if new:
                w.writeheader()
            w.writerow(info)
        print(f"저장: {path}  ({info['rec_s']} s, {info['channels']}채널, 최대 {info['peak']:.2f}, 소리 시작 약 {info['play_offset_s']} s)")
        if info["peak"] >= 0.99:
            print("  ! 녹음이 찌그러졌다. 앰프 볼륨을 낮춘다.")
        elif info["peak"] < 0.01:
            print("  ! 소리가 거의 녹음되지 않았다. 스피커·볼륨·마이크를 확인한다.")
        if info["warnings"]:
            print(f"  ! 녹음 중 경고: {info['warnings']} (표본이 빠졌을 수 있다. 다른 프로그램을 닫고 다시 한다.)")


def cmd_selftest(args):
    """노트북 스피커로 1 kHz를 내고 노트북 마이크로 받아, 녹음이 소리를 앞뒤로 다 담는지 본다. 녹음은 저장하지 않는다."""
    sio = SoundIO(mic=args.mic or "default", speaker=args.out)
    print(f"마이크: {sio._name(sio.mic)} / 출력: {sio._name(sio.speaker)}")
    print("1 kHz 소리가 약 3초 나온다 ...")
    rec, info = sio.play_and_record("exp1_tone_1k", "A", volume=1.0)
    x = rec[:, 0].astype(np.float32) / 32768
    onset = find_onset(x, PRE_ROLL)
    print(f"녹음 길이 {info['rec_s']} s, 소리 길이 {info['sound_s']} s, 재생 시작 추정 {info['play_offset_s']} s")
    if onset is None:
        print("결과: 실패 - 녹음에서 소리를 찾지 못했다. 이어폰을 빼고 노트북 스피커로 하거나, 이어폰을 마이크 가까이 둔다.")
        return 1
    t_on = onset / FS
    tail = info["rec_s"] - (t_on + info["sound_s"])
    print(f"녹음 시작 후 {t_on:.3f} s에 소리가 들어왔다. 소리가 끝난 뒤 {tail:.3f} s 더 녹음했다.")
    if t_on > 0.05 and tail > 0.05:
        print("결과: 통과 - 녹음이 소리보다 먼저 시작하고 늦게 끝난다.")
        return 0
    print("결과: 확인 필요 - 소리 앞이나 뒤가 잘렸을 수 있다. 이 출력을 그대로 Claude에게 보여 준다.")
    return 1


def main(argv=None):
    p = argparse.ArgumentParser(description="소리 재생 + UMA-16 동시 녹음")
    p.add_argument("--mic", help="입력 장치 (기본: UMA-16 자동 찾기, 'default' = 노트북 마이크)")
    p.add_argument("--out", help="출력 장치 (기본: 시스템 기본 출력)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices", help="장치 목록")
    pp = sub.add_parser("play", help="재생만")
    pp.add_argument("sounds", nargs="+")
    pp.add_argument("--speaker", default="A", choices=["A", "B", "AB", "a", "b", "ab"])
    pp.add_argument("--gap", type=float, default=1.0, help="파일 사이 쉬는 시간 (s)")
    pp.add_argument("--repeat", type=int, default=1, help="반복 횟수 (0 = Ctrl+C까지)")
    pp.add_argument("--volume", type=float, default=VOLUME, help="0~1, 처음엔 낮게")
    pr = sub.add_parser("rec", help="재생하면서 녹음")
    pr.add_argument("sounds", nargs="+")
    pr.add_argument("--speaker", default="A", choices=["A", "B", "AB", "a", "b", "ab"])
    pr.add_argument("--volume", type=float, default=VOLUME, help="0~1, 처음엔 낮게")
    pr.add_argument("--out-dir", default=str(REC_DIR))
    sub.add_parser("selftest", help="노트북 스피커·마이크로 동시 시작 확인")
    args = p.parse_args(argv)
    if sd is None:
        print("sounddevice가 설치되어 있지 않다. 'python -m pip install sounddevice'를 실행한다.")
        return 1
    return {"devices": cmd_devices, "play": cmd_play, "rec": cmd_rec, "selftest": cmd_selftest}[args.cmd](args) or 0


if __name__ == "__main__":
    sys.exit(main())
