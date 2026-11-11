"""장치 없이 하는 시험. 실행: python test_sound_io.py  (소리가 나지 않는다)"""
import numpy as np

import sound_io as s


def test_all_signals_load():
    names = sorted(p.stem for p in s.SIGNAL_DIR.glob("*.wav"))
    assert len(names) == 13, names
    for n in names:
        x = s.load_signal(n)
        assert x.ndim == 2 and x.shape[1] == 2 and x.dtype == np.float32, n
        assert 0.4 < np.abs(x).max() <= 0.51, n          # −6 dBFS ≈ 0.501


def test_route():
    a_only = s.load_signal("exp3_white")                  # 오른쪽이 비어 있는 파일
    assert not np.any(a_only[:, 1])
    a = s.route(a_only, "A")
    assert np.any(a[:, 0]) and not np.any(a[:, 1])
    b = s.route(a_only, "b")                              # A 전용 파일을 B로 → 오른쪽으로 옮겨짐
    assert not np.any(b[:, 0]) and np.array_equal(b[:, 1], a_only[:, 0])

    both = s.load_signal("exp2_band_4k")                  # 좌우 다른 잡음
    assert np.any(both[:, 0]) and np.any(both[:, 1])
    assert np.array_equal(s.route(both, "A")[:, 0], both[:, 0]) and not np.any(s.route(both, "A")[:, 1])
    assert np.array_equal(s.route(both, "B")[:, 1], both[:, 1]) and not np.any(s.route(both, "B")[:, 0])
    assert np.array_equal(s.route(both, "AB"), both)

    try:
        s.route(both, "C")
        assert False
    except ValueError:
        pass


def test_volume():
    full = s.SoundIO._prepare("exp3_white", "A", 1.0)
    low = s.SoundIO._prepare("exp3_white", "A", 0.3)
    assert low.dtype == np.float32 and np.allclose(low, full * 0.3, atol=1e-6)
    for bad in (0, -0.1, 1.5):
        try:
            s.SoundIO._prepare("exp3_white", "A", bad)
            assert False
        except ValueError:
            pass


def test_save_roundtrip():
    import tempfile
    from pathlib import Path
    import soundfile as sf
    rec = (np.random.default_rng(1).standard_normal((4800, 16)) * 3000).astype(np.int16)
    with tempfile.TemporaryDirectory() as d:
        p = s.SoundIO.save(rec, Path(d) / "a" / "x.wav")
        back, fs = sf.read(str(p), dtype="int16")
        info = sf.info(str(p))
    assert fs == s.FS and info.channels == 16 and info.subtype == "PCM_16"
    assert np.array_equal(back, rec)


def _dev(name, hostapi, ins, outs):
    return {"name": name, "hostapi": hostapi, "max_input_channels": ins, "max_output_channels": outs}


WIN_APIS = [
    {"name": "MME", "default_input_device": 0, "default_output_device": 2},
    {"name": "Windows DirectSound", "default_input_device": 3, "default_output_device": 4},
    {"name": "Windows WASAPI", "default_input_device": 5, "default_output_device": 6},
]
WIN_DEVS = [
    _dev("마이크 배열(Realtek)", 0, 2, 0),
    _dev("마이크(UMA16v2)", 0, 2, 0),                   # MME는 2채널만 보일 수 있다
    _dev("헤드폰(Realtek)", 0, 0, 2),
    _dev("주 사운드 캡처 드라이버", 1, 2, 0),
    _dev("주 사운드 드라이버", 1, 0, 2),
    _dev("마이크 배열(Realtek)", 2, 2, 0),
    _dev("헤드폰(Realtek)", 2, 0, 2),
    _dev("마이크(UMA16v2)", 2, 16, 0),
]
MAC_APIS = [{"name": "Core Audio", "default_input_device": 0, "default_output_device": 1}]
MAC_DEVS = [
    _dev("MacBook Air Microphone", 0, 1, 0),
    _dev("MacBook Air Speakers", 0, 0, 2),
    _dev("UMA16v2", 0, 16, 0),
]


def test_pick_windows():
    assert s.pick_device(WIN_DEVS, WIN_APIS, s.MIC_HINTS, "input", 0) == 7          # WASAPI 16채널
    assert s.pick_device(WIN_DEVS, WIN_APIS, None, "output", 2) == 6                # WASAPI 기본 출력
    assert s.pick_device(WIN_DEVS, WIN_APIS, "default", "input", 0) == 5
    assert s.pick_device(WIN_DEVS, WIN_APIS, "헤드폰", "output", 2) == 6
    assert s.pick_device(WIN_DEVS, WIN_APIS, "3", "input", 0) == 3


def test_pick_mac():
    assert s.pick_device(MAC_DEVS, MAC_APIS, s.MIC_HINTS, "input", 0) == 2
    assert s.pick_device(MAC_DEVS, MAC_APIS, None, "output", 1) == 1
    assert s.pick_device(MAC_DEVS, MAC_APIS, "uma-16", "input", 0) == 2


def test_pick_missing():
    try:
        s.pick_device(MAC_DEVS[:2], MAC_APIS, s.MIC_HINTS, "input", 0)
        assert False
    except LookupError:
        pass


def test_find_onset():
    fs, pre = s.FS, s.PRE_ROLL
    rng = np.random.default_rng(0)
    x = rng.standard_normal(int(fs * 3)).astype(np.float32) * 0.001
    start = int(fs * 0.42)
    t = np.arange(fs) / fs
    x[start:start + fs] += 0.3 * np.sin(2 * np.pi * 1000 * t)
    on = s.find_onset(x, pre)
    assert abs(on - start) < fs * 0.002, on
    assert s.find_onset(rng.standard_normal(fs * 2).astype(np.float32) * 0.001, pre) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("통과:", name)
    print("모두 통과")
